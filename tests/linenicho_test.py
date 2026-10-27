"""Agente (nicho) fixo por número: quem chama um número com agente definido sempre cai nele, sem roteamento por palavras-chave."""
import asyncio, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
async def main():
    S = harness.load_server()
    with S.conn() as c:
        c.execute("INSERT INTO lines(id,label,active,created) VALUES('comercial2','Comercial 2',1,?)", (time.time(),))
        solar = c.execute("INSERT INTO niches(name,prompt,outbound_text,keywords,created) VALUES('Solar','p','o','zzsolar',?)", (time.time(),)).lastrowid
    harness.GWL["comercial2"] = {"state": "open", "me": "5521999991111"}
    ls = {l["id"]: l for l in S.line_summary()}
    check("por padrão o número está em automático", ls["comercial2"]["niche_id"] == 0 and S.line_niche("comercial2") is None)
    # automático: palavra-chave decide
    await S.handle_incoming("5521955500001", "A", "quero zzsolar", send=False, line="comercial2")
    check("em automático, a palavra-chave decide", S.get_lead("5521955500001")["niche_id"] == solar, S.get_lead("5521955500001"))
    # fixo no Planos (id 1), mesmo falando de energia solar
    await S.lines_put("comercial2", {"niche_id": 1})
    check("o resumo mostra o agente fixado", [l for l in S.line_summary() if l["id"] == "comercial2"][0]["niche_id"] == 1)
    await S.handle_incoming("5521955500002", "B", "quero zzsolar", send=False, line="comercial2")
    check("número fixo ignora as palavras-chave", S.get_lead("5521955500002")["niche_id"] == 1, S.get_lead("5521955500002"))
    # outro número não é afetado
    await S.handle_incoming("5521955500003", "C", "quero zzsolar", send=False, line="main")
    check("outro número continua em automático", S.get_lead("5521955500003")["niche_id"] == solar)
    # fixo sem palavra-chave nenhuma
    await S.lines_put("comercial2", {"niche_id": solar})
    await S.handle_incoming("5521955500004", "D", "oi, boa tarde", send=False, line="comercial2")
    check("fixo também vale para mensagem sem palavra-chave", S.get_lead("5521955500004")["niche_id"] == solar)
    # validação e limpeza
    try:
        await S.lines_put("comercial2", {"niche_id": 999}); ok = False
    except Exception: ok = True
    check("agente inexistente é recusado", ok)
    await S.lines_put("comercial2", {"niche_id": 0})
    check("voltar para automático", S.line_niche("comercial2") is None)
    # lead que já existe não muda de agente
    await S.lines_put("comercial2", {"niche_id": solar})
    await S.handle_incoming("5521955500002", "B", "oi de novo", send=False, line="comercial2")
    check("lead existente mantém o agente em que já estava", S.get_lead("5521955500002")["niche_id"] == 1)
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
