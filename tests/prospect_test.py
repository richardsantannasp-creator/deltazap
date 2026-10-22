"""Prospecção (Google Places): busca em modo demonstração, só WhatsApp confirmado, supressão, fila com consentimento registrado, bloqueio de rede interna."""
import asyncio, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
os.environ["PROSPECT_DEMO"] = "1"
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
async def expect(coro, frag):
    try:
        await coro
    except Exception as e:
        return frag in str(getattr(e, "detail", e))
    return False
async def main():
    S = harness.load_server()
    check("modo demo ativo na configuração", (await S.prospect_config())["demo"])
    check("pede termo e cidade", await expect(S.prospect_search(S.ProspectSearchIn(terms="", city="")), "nicho"))
    r = await S.prospect_search(S.ProspectSearchIn(terms="dentista", city="Guarulhos SP", sites=True))
    j = S.PROSPECT_JOBS[r["job_id"]]
    for _ in range(200):
        if j["state"] != "rodando": break
        await asyncio.sleep(0.1)
    check("busca conclui sem erro", j["state"] == "concluido", j)
    d = await S.prospect_list()
    rows = d["rows"]
    check("empresas salvas e busca no histórico", len(rows) > 50 and len(d["searches"]) == 1, len(rows))
    conf = [x for x in rows if x["wa_origin"] == "Site da empresa"]
    prov = [x for x in rows if x["whatsapp"] and x["wa_origin"] != "Site da empresa"]
    check("há WhatsApp confirmado no site e provável celular", conf and prov, (len(conf), len(prov)))
    # repetir a busca não duplica nem apaga status
    await S.prospect_patch(conf[0]["place_id"], S.ProspectPatchIn(status="Contatado", notes="ligou"))
    r2 = await S.prospect_search(S.ProspectSearchIn(terms="dentista", city="Guarulhos SP", sites=False))
    j2 = S.PROSPECT_JOBS[r2["job_id"]]
    for _ in range(100):
        if j2["state"] != "rodando": break
        await asyncio.sleep(0.1)
    d2 = await S.prospect_list()
    keep = [x for x in d2["rows"] if x["place_id"] == conf[0]["place_id"]][0]
    check("nova busca igual: sem duplicar, mantém status e nota", len(d2["rows"]) == len(rows) and keep["status"] == "Contatado" and keep["notes"] == "ligou" and j2["new"] == 0)
    await S.prospect_patch(conf[0]["place_id"], S.ProspectPatchIn(status="Novo"))
    # importar exige confirmação
    ids = [x["place_id"] for x in conf[:5]]
    check("sem a confirmação não enfileira", await expect(S.prospect_import(S.ProspectImportIn(ids=ids, niche_id=1), harness.BackgroundTasks()), "base legal"))
    # bloqueado não entra
    blocked = conf[1]
    await S.prospect_patch(blocked["place_id"], S.ProspectPatchIn(status="Não contatar"))
    check("«Não contatar» entra na lista de supressão", S.is_suppressed(blocked["whatsapp"]))
    res = await S.prospect_import(S.ProspectImportIn(ids=ids + [prov[0]["place_id"]], niche_id=1, ack=True), harness.BackgroundTasks())
    check("enfileira só confirmados e não bloqueados (provável fica de fora)", res["queued"] == 4 and res["skipped"]["provavel"] == 1 and res["skipped"]["nao_contatar"] + res["suppressed"] >= 1, res)
    with S.conn() as c:
        ob = [dict(x) for x in c.execute("SELECT phone,consent,context FROM outbox WHERE status='queued'")]
    check("origem do consentimento registrada em cada item da fila", ob and all("Prospecção B2B" in x["consent"] and "legítimo interesse" in x["consent"] for x in ob), ob[:1])
    check("contexto diz que veio do Google", all("Google" in x["context"] for x in ob))
    st = {x["place_id"]: x["status"] for x in (await S.prospect_list())["rows"]}
    check("status vira «Na fila»", st[ids[0]] == "Na fila", st[ids[0]])
    res2 = await S.prospect_import(S.ProspectImportIn(ids=[prov[0]["place_id"]], niche_id=1, ack=True, include_probable=True), harness.BackgroundTasks())
    check("com «incluir provável» entra", res2["queued"] == 1, res2)
    check("só provável sem a opção: erro claro", await expect(S.prospect_import(S.ProspectImportIn(ids=[prov[1]["place_id"]], niche_id=1, ack=True), harness.BackgroundTasks()), "WhatsApp confirmado"))
    ex = await S.prospect_export(S.ProspectExportIn(ids=[x["place_id"] for x in rows]))
    check("exportação não leva bloqueados", blocked["whatsapp"] not in ex["csv"] and conf[2]["whatsapp"] in ex["csv"])
    # purge: o que não virou fila some depois de 30 dias
    with S.conn() as c:
        c.execute("UPDATE prospects SET created=? WHERE queued_at IS NULL", (time.time() - 31 * 86400,))
    S.prospect_purge()
    left = (await S.prospect_list())["rows"]
    check("passados 30 dias só ficam os que viraram fila", left and all(x["status"] == "Na fila" for x in left), len(left))
    # SSRF
    import places_enrich as E
    check("bloqueia site que aponta para a rede interna", not E.url_publica("http://127.0.0.1:8000/x") and not E.url_publica("http://169.254.169.254/") and not E.url_publica("file:///etc/passwd"))
    check("aceita endereço público", E.url_publica("http://1.1.1.1/"))
    check("extrai WhatsApp, e-mail e Instagram do HTML", E.extrair('<a href="https://wa.me/5511987654321?text=oi">x</a> mailto:contato@loja.com.br instagram.com/loja_x')[0] == ["+5511987654321"])
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
