"""Nicho pronto 'Energia solar — Vendas': carrega da pasta niches/, traz variações e só dispara depois de preencher a empresa."""
import asyncio, os, sys, tempfile
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
    n = next((x for x in await S.niches() if x["name"].startswith("Energia solar")), None)
    check("nicho carregado da pasta niches/", n is not None)
    n = S.get_niche(n["id"])
    check("abertura e variações com SAIR e {agente}", "SAIR" in n["outbound_text"] and len(S.parse_variants(n["outbound_variants"])) == 2 and all("SAIR" in v for v in S.parse_variants(n["outbound_variants"])) and "{agente}" in n["outbound_text"], n["outbound_variants"])
    check("prompt traz as 8 etapas do roteiro e não deixa inventar números", "PEDIR A CONTA DE ENERGIA" in n["prompt"] and "RETOMADAS" in n["prompt"] and "Nunca invente nem estime preço" in n["prompt"])
    check("leitura da conta de energia configurada", "kWh" in n["doc_hint"])
    pend = S.unfilled_fields(n)
    check("só falta o nome da empresa", pend == ["[NOME DA EMPRESA]"], pend)
    r = await S.dispatch_one(n, "5521933330001", "Rita", "")
    check("não dispara com [NOME DA EMPRESA] pendente", "sem preencher" in str(r), r)
    for k in ("outbound_text", "outbound_variants", "prompt"):
        with S.conn() as c: c.execute(f"UPDATE niches SET {k}=REPLACE({k},'[NOME DA EMPRESA]','Sol Forte') WHERE id=?", (n["id"],))
    n = S.get_niche(n["id"])
    r = await S.dispatch_one(n, "5521933330002", "Rita", "", line="main")
    check("sem nome do agente, pede para definir", "nome do agente" in str(r), r)
    with S.conn() as c: c.execute("UPDATE niches SET agent_name='Ana' WHERE id=?", (n["id"],))
    r = await S.dispatch_one(S.get_niche(n["id"]), "5521933330003", "Rita", "")
    with S.conn() as c: t = c.execute("SELECT text FROM messages WHERE phone='5521933330003' AND role='sdr' ORDER BY id DESC LIMIT 1").fetchone()["text"]
    check("depois de preencher, a abertura sai com empresa e nome", r == "ok" and "Sol Forte" in t and "Aqui é Ana" in t or "Sou Ana" in t, (r, t))
    # roteamento receptivo pela palavra-chave
    check("lead que pergunta de energia solar cai neste agente", S.route_niche("quero orçamento de energia solar")[0] == n["id"])
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
