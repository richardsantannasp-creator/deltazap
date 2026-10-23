"""Prontidão da API oficial: checklist, qualidade do número, status dos templates, templates prontos e teste de envio."""
import asyncio, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
def st(d, i): return next(x for x in d["items"] if x["id"] == i)
async def main():
    S = harness.load_server()
    d = await S.official_readiness()
    check("sem chaves: token, número, segredo e verificação aparecem como erro e não está pronto", all(st(d, i)["status"] == "erro" for i in ("token", "phone", "secret", "verify")) and not d["ready"], d["items"])
    check("em modo QR avisa que nada muda até trocar PROVIDER", st(d, "provider")["status"] == "aviso" and "PROVIDER=official" in st(d, "provider")["help"])
    check("mostra a URL do webhook", d["webhook_url"].endswith("/webhook"))
    S.WA_TOKEN, S.WA_PHONE_ID, S.APP_SECRET, S.VERIFY_TOKEN, S.WA_WABA, S.PROVIDER = "tok", "123", "sec", "meu-token-longo", "waba1", "official"
    d = await S.official_readiness()
    check("com tudo preenchido e Meta ok: pronto", d["ready"] and st(d, "number")["status"] == "ok" and "Minha Corretora" in st(d, "number")["detail"], d["items"])
    check("qualidade verde", st(d, "quality")["status"] == "ok" and "TIER_250" in st(d, "quality")["detail"])
    harness.WASIM["phone"]["quality_rating"] = "RED"
    d = await S.official_readiness()
    check("qualidade vermelha vira erro com orientação", st(d, "quality")["status"] == "erro" and "opt-in" in st(d, "quality")["help"])
    harness.WASIM["phone_status"] = 401
    d = await S.official_readiness()
    check("token recusado pela Meta: erro claro e não pronto", st(d, "number")["status"] == "erro" and not d["ready"])
    harness.WASIM["phone_status"] = 200
    ids = [x for x in d["items"] if x["id"].startswith("tpl_")]
    check("nicho sem template: aviso", ids and all(x["status"] == "aviso" for x in ids), ids)
    with S.conn() as c:
        c.execute("UPDATE niches SET template='planos_de_saude_abertura' WHERE id=1")
    d = await S.official_readiness()
    check("template aprovado na Meta aparece como ok", st(d, "tpl_1")["status"] == "ok" and "APPROVED" in st(d, "tpl_1")["detail"], st(d, "tpl_1"))
    harness.WASIM["templates"] = [{"name": "planos_de_saude_abertura", "status": "PENDING"}]
    d = await S.official_readiness()
    check("template pendente: aviso", st(d, "tpl_1")["status"] == "aviso" and "PENDING" in st(d, "tpl_1")["detail"])
    check("webhook: ainda não chamado", st(d, "webhook")["status"] == "aviso")
    S.set_setting("wa_webhook_last", str(time.time()))
    d = await S.official_readiness()
    check("webhook: última chamada registrada", st(d, "webhook")["status"] == "ok")
    # templates prontos
    t = await S.official_templates()
    ab = [x for x in t["templates"] if x["niche_id"] == 1][0]
    check("abertura vira {{1}} com SAIR e nome em minúsculas", "{{1}}" in ab["body"] and "{nome}" not in ab["body"] and "SAIR" in ab["body"] and ab["name"] == "planos_de_saude_abertura", ab)
    check("as 3 retomadas vêm prontas, todas com SAIR", len([x for x in t["templates"] if x["name"].startswith("retomada_")]) == 3 and all("SAIR" in x["body"] and "{{1}}" in x["body"] for x in t["templates"] if x["name"].startswith("retomada_")))
    with S.conn() as c:
        c.execute("UPDATE niches SET outbound_text='Olá {nome}, aqui é a [NOME] da {empresa}.' WHERE id=1")
    t = await S.official_templates()
    ab = [x for x in t["templates"] if x["niche_id"] == 1][0]
    check("campos pendentes e {empresa} são tratados", ab["pending"] == ["[NOME]"] and "{empresa}" not in ab["body"] and ab["note"], ab)
    # teste de envio
    r = await S.official_test_template(S.TplTestIn(phone="(21) 99999-0000", template="planos_de_saude_abertura"))
    sent = [g for g in harness.MEDIA["graph"] if g["json"] and g["json"].get("type") == "template"][-1]["json"]
    check("teste de template é enviado ao número informado, com o nome como variável", r["ok"] and sent["to"].endswith("999990000") and sent["template"]["name"] == "planos_de_saude_abertura" and sent["template"]["components"][0]["parameters"][0]["text"] == "Teste", sent)
    harness.WASIM["tpl_error"] = 1
    r = await S.official_test_template(S.TplTestIn(phone="21999990000", template="inexistente"))
    check("erro da Meta chega ao painel com o código", not r["ok"] and "132001" in r["error"], r)
    for bad in (S.TplTestIn(phone="abc", template="x"), S.TplTestIn(phone="21999990000", template="Nome Inválido!")):
        try:
            await S.official_test_template(bad); ok = False
        except Exception: ok = True
        check("entrada inválida é recusada", ok)
    S.WA_TOKEN = ""
    try:
        await S.official_test_template(S.TplTestIn(phone="21999990000", template="x")); ok = False
    except Exception as e: ok = "WHATSAPP_TOKEN" in str(getattr(e, "detail", e))
    check("sem chaves o teste explica o que falta", ok)
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
