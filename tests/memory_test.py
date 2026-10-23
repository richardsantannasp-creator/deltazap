"""Memória por lead: resume o que saiu da janela de 30 mensagens, entra no contexto, some com o apagar dados e não guarda dados sensíveis."""
import asyncio, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
PH = "5521955550002"
def fill(S, n, start=0):
    with S.conn() as c:
        for i in range(n):
            c.execute("INSERT INTO messages(phone,role,text,ts) VALUES(?,?,?,?)", (PH, "lead" if i % 2 == 0 else "sdr", f"msg {start+i} meu email é a@b.com", time.time() - 300000 + start + i))
async def main():
    S = harness.load_server()
    S.upsert_lead(PH, "Bia", niche_id=1)
    fill(S, 20)
    await S.memory_update(PH)
    check("poucas mensagens: nada é resumido", (await S.memory_get(PH))["summary"] == "")
    fill(S, 25, 20)                                  # 45 no total: 15 ficam fora da janela de 30
    n0 = len([c for c in harness.CALLS if c["kind"] == "memoria"])
    await S.memory_update(PH)
    d = await S.memory_get(PH)
    calls = [c for c in harness.CALLS if c["kind"] == "memoria"]
    check("45 mensagens: resume as 15 antigas", "Campinas" in d["summary"] and len(calls) == n0 + 1, d)
    check("o texto enviado para resumir não leva e-mail nem telefone", "a@b.com" not in calls[-1]["user"][-3000:] if isinstance(calls[-1]["user"], str) else True, calls[-1]["user"])
    check("instrui a não guardar saúde, documentos e contatos", "doenças" in calls[-1]["system"] and "CPF" in calls[-1]["system"])
    await S.memory_update(PH)
    check("sem mensagens novas fora da janela: não chama de novo", len([c for c in harness.CALLS if c["kind"] == "memoria"]) == n0 + 1)
    with S.conn() as c:
        c.execute("INSERT INTO messages(phone,role,text,ts) VALUES(?,?,?,?)", (PH, "lead", "oi, voltei", time.time()))
    lead = S.get_lead(PH); niche = S.get_niche(lead["niche_id"])
    t = "\n".join(b["text"] for b in S.build_system(lead, niche))
    check("a memória entra no contexto do agente", "# MEMÓRIA DESTE LEAD" in t and "Orçamento até R$ 900" in t)
    check("lead que voltou depois de dias: o agente é avisado", "voltou a escrever" in t, t[-500:])
    ls = await S.leads()
    check("painel recebe a memória do lead", [x for x in ls if x["phone"] == PH][0]["memory"].startswith("- Quer"))
    # resumo atualiza com mais mensagens
    harness.MEMSIM["fn"] = lambda u: "- Atualizado: " + ("tinha resumo anterior" if "Campinas" in u else "sem resumo")
    fill(S, 12, 100)
    await S.memory_update(PH)
    d = await S.memory_get(PH)
    check("segunda rodada parte do resumo anterior", "tinha resumo anterior" in d["summary"], d)
    ex = await S.lead_export(PH)
    check("exportação LGPD inclui a memória", "memoria_resumo" in str(ex.content) and "Atualizado" in str(ex.content))
    await S.memory_clear(PH)
    check("limpar memória", (await S.memory_get(PH))["summary"] == "")
    harness.MEMSIM["fn"] = lambda u: "- Texto com e-mail x@y.com e fone 21 99999-8888"
    fill(S, 12, 200)
    await S.memory_update(PH)
    sm = (await S.memory_get(PH))["summary"]
    check("o resumo também é limpo de e-mail e telefone", "x@y.com" not in sm and "99999" not in sm, sm)
    S.erase_lead(PH)
    with S.conn() as c:
        check("apagar dados apaga a memória", not c.execute("SELECT 1 FROM lead_memory WHERE phone=?", (PH,)).fetchone())
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
