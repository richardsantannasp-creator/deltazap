"""Revisão antes de enviar: valores, percentuais e prazos precisam existir na base, no catálogo ou na fala do lead."""
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
PH = "5521955550001"
async def ask(S, text, hook):
    harness.AGENT_HOOK["fn"] = hook
    with S.conn() as c:
        c.execute("DELETE FROM messages WHERE phone=?", (PH,))
    S.upsert_lead(PH, "Bia", niche_id=1)
    with S.conn() as c:
        c.execute("INSERT INTO messages(phone,role,text,ts) VALUES(?,?,?,?)", (PH, "lead", text, S.time.time()))
    return await S.run_agent(PH)
async def main():
    S = harness.load_server()
    S.set_setting("review_on", "1")
    with S.conn() as c:
        c.execute("INSERT INTO kb_docs(niche_id,title,body,ts) VALUES(1,'Preços','Plano Essencial: R$ 489,90 por mês. Desconto de 10% no plano anual. Retorno do corretor em até 2 horas úteis.',?)", (S.time.time(),))
    # 1) tudo da base: passa direto
    r = await ask(S, "quanto custa?", lambda t, s: "O Essencial sai R$ 489,90 por mês, com 10% no anual, e o corretor responde em até 2 horas.")
    check("valores da base passam sem mudança", "489,90" in r and "10%" in r, r)
    # 2) valor inventado: reescreve
    calls = []
    def h2(t, s):
        calls.append(t)
        return "O plano sai R$ 321,00 por mês." if "revisão interna" not in t else "Posso te passar o valor oficial pelo corretor. Para quantas pessoas é?"
    r = await ask(S, "e o preço?", h2)
    check("valor inventado: o agente reescreve sem ele", "321" not in r and "corretor" in r and len(calls) == 2, (r, calls))
    # 3) insiste no erro: corta a frase / resposta segura
    r = await ask(S, "e o preço?", lambda t, s: "Fica R$ 321,00 por mês. Posso te ajudar com mais algo?")
    check("insistiu no valor inventado: frase removida, resto mantido", "321" not in r and "mais algo" in r, r)
    r = await ask(S, "e o preço?", lambda t, s: "Fica R$ 321,00 por mês.")
    check("só tinha o valor inventado: resposta segura", r == S.REVIEW_SAFE, r)
    # 4) percentual e prazo
    r = await ask(S, "tem desconto?", lambda t, s: "Temos 35% de desconto hoje!" if "revisão" not in t else "Há desconto no plano anual, o corretor confirma.")
    check("desconto fora da base é barrado", "35%" not in r, r)
    r = await ask(S, "quando retornam?", lambda t, s: "Retornamos em 15 minutos." if "revisão" not in t else "O corretor retorna em até 2 horas úteis.")
    check("prazo fora da base é barrado e o oficial passa", "15 minutos" not in r and "2 horas" in r, r)
    # 5) o que o lead disse vale
    r = await ask(S, "tenho até R$ 900 por mês", lambda t, s: "Anotei: orçamento de até R$ 900 por mês.")
    check("valor dito pelo lead pode ser repetido", "900" in r, r)
    # 6) catálogo
    with S.conn() as c:
        c.execute("INSERT INTO products(niche_id,name,description,price_cents,unit,max_discount_pct,active,ts) VALUES(1,'Premium','',129900,'mês',5,1,?)", (S.time.time(),))
    r = await ask(S, "e o premium?", lambda t, s: "O Premium custa R$ 1.299,00 e aceitamos até 5% de desconto.")
    check("preço e desconto do catálogo passam", "1.299,00" in r and "5%" in r, r)
    # 7) registro e interruptor
    d = await S.review_get()
    check("ocorrências ficam registradas, sem o telefone completo", d["count_30d"] >= 4 and all(PH not in x["who"] for x in d["rows"]) and d["rows"][0]["original"], d["rows"][:1])
    await S.review_put(S.ReviewIn(enabled=False))
    r = await ask(S, "e o preço?", lambda t, s: "Fica R$ 321,00 por mês.")
    check("desligada: não interfere", "321" in r, r)
    await S.review_put(S.ReviewIn(enabled=True))
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
