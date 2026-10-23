"""Variações da abertura: rodízio equilibrado, SAIR garantido, campos pendentes bloqueiam, geração com o Claude e medição por variação."""
import asyncio, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
BASE = dict(name="Planos de saúde", prompt="x", outbound_text="Olá {nome}, aqui é a Ana da Vida Mais. Posso te fazer 3 perguntas? Se não quiser receber mensagens, responda SAIR.")
async def main():
    S = harness.load_server()
    n = S.get_niche(1)
    check("sem variações: sempre a principal", S.pick_opening(n) == (0, n["outbound_text"]))
    await S.niche_update(1, S.NicheIn(**BASE, outbound_variants="Oi {nome}! Sou a Ana, assistente virtual da Vida Mais, e vi seu pedido. Quer ver opções?\n---\ncurta\n---\n  \n---\nOlá {nome}, tudo bem? Ana, assistente virtual da Vida Mais. Posso ajudar com seu plano de saúde? Responda SAIR para parar."))
    n = S.get_niche(1)
    vs = S.parse_variants(n["outbound_variants"])
    check("variações curtas/vazias são descartadas e o SAIR é acrescentado quando falta", len(vs) == 2 and all("SAIR" in v for v in vs), vs)
    # disparo: rodízio equilibrado
    used = []
    for i in range(9):
        ph = f"55219{i:08d}"
        await S.dispatch_one(S.get_niche(1), ph, f"Lead{i}", "")
        used.append(S.get_lead(ph)["opening_variant"])
    check("9 envios com 3 aberturas: 3 de cada", sorted(used) == [0, 0, 0, 1, 1, 1, 2, 2, 2], used)
    msgs = {S.get_lead(f"55219{i:08d}")["opening_variant"]: None for i in range(9)}
    with S.conn() as c:
        texts = [r["text"] for r in c.execute("SELECT text FROM messages WHERE role='sdr' AND phone LIKE '55219%'")]
    import re
    uniq = {re.sub(r"Lead\d", "{nome}", t) for t in texts}
    check("textos enviados são diferentes entre si e todos trazem o SAIR", len(uniq) == 3 and all("SAIR" in t for t in texts), uniq)
    check("o nome do lead entra em todas as variações", all("Lead" in t for t in texts))
    # campos pendentes nas variações bloqueiam
    await S.niche_update(1, S.NicheIn(**BASE, outbound_variants="Oi {nome}! Aqui é a [NOME] da Vida Mais, assistente virtual. Posso ajudar? Se não quiser, responda SAIR."))
    res = await S.dispatch_one(S.get_niche(1), "5521900000099", "Zé", "")
    check("variação com [CAMPO] pendente bloqueia o envio", "sem preencher" in str(res), res)
    # geração
    await S.niche_update(1, S.NicheIn(**BASE))
    g = await S.variants_generate(1)
    check("Claude gera variações, todas com SAIR, para revisar antes de salvar", len(g["variants"]) == 3 and all("SAIR" in v for v in g["variants"]), g)
    check("gerar não salva sozinho", S.get_niche(1)["outbound_variants"] == "")
    try:
        await S.variants_generate(999); ok = False
    except Exception: ok = True
    check("nicho inexistente é recusado", ok)
    # medição por variação
    await S.niche_update(1, S.NicheIn(**BASE, outbound_variants=g["variants"][0]))
    with S.conn() as c:
        c.execute("DELETE FROM leads WHERE phone LIKE '55219%'"); c.execute("DELETE FROM outbox"); c.execute("DELETE FROM messages WHERE phone LIKE '55219%'")
        for i in range(10):
            ph = f"55219{i:08d}"; v = i % 2
            c.execute("INSERT INTO leads(phone,name,stage,created,niche_id,test,origin,opening_variant) VALUES(?,?,?,?,1,0,'ativo',?)", (ph, "x", "contatado", time.time() - 3600, v))
            c.execute("INSERT INTO outbox(phone,niche_id,status,created,sent_at) VALUES(?,1,'sent',?,?)", (ph, time.time() - 3500, time.time() - 3500))
            if v == 1 and i < 8: c.execute("INSERT INTO messages(phone,role,text,ts) VALUES(?,?,?,?)", (ph, "lead", "oi", time.time() - 3000))
    r = S.insights_report(1, 30)
    o = {x["variant"]: x for x in r["openings"]}
    check("Funil mostra a resposta de cada abertura", o[0]["sent"] == 5 and o[0]["reply_pct"] == 0 and o[1]["sent"] == 5 and o[1]["reply_pct"] == 80 and o[1]["label"] == "Variação 1", r["openings"])
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
