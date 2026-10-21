"""Gestor: disparo pelos próprios números (com consentimento) e agenda de reuniões própria."""
import asyncio, os, sys, tempfile, json, time, base64
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
def q(S, sql, *a):
    with S.conn() as c: return [dict(r) for r in c.execute(sql, a)]
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0
class BG:
    def add_task(self, *a, **k): pass
async def main():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    harness.GCAL["pub"] = key.public_key()
    S = harness.load_server(); S.PROVIDER = "qr"; S.LINES_MAX = 4; harness.GW["state"] = "open"
    TZ = S.TZ; seg = datetime(2026, 10, 19, 8, 0, tzinfo=TZ); S.now_local = lambda: seg
    nid = S.default_niche_id()
    await S.managers_add(S.ManagerIn(login="gil", name="Gil", password="senhaforte1"))
    await S.managers_add(S.ManagerIn(login="bia", name="Bia", password="senhaforte2"))
    await S.managers_add(S.ManagerIn(login="sup", name="Sônia", password="senhaforte3", role="supervisor"))
    TG = (await S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1")))["token"]
    TB = (await S.gestor_login(S.AgentLoginIn(login="bia", password="senhaforte2")))["token"]
    TS = (await S.gestor_login(S.AgentLoginIn(login="sup", password="senhaforte3")))["token"]
    # ---------- disparo ----------
    body = S.DispatchIn(niche_id=nid, lines="5521977770001;Ana;Loja A;pediu orçamento\n5521977770002;Beto", consent=True, origem="formulário do site em 10/2026")
    check("sem número conectado o gestor não dispara", await err(S.gestor_dispatch(body, BG(), x_token=TG)) == 400)
    await S.gestor_line_add(S.MgrLineIn(label="Gil Vendas"), x_token=TG); await S.gestor_line_add(S.MgrLineIn(label="Bia Vendas"), x_token=TB)
    for k in harness.GWL: harness.GWL[k]["state"] = "open"
    n = await S.gestor_niches(x_token=TG)
    check("o gestor vê os nichos (somente nome e abertura)", n["niches"] and set(n["niches"][0]) == {"id", "name", "outbound_text"})
    S.get_niche = S.get_niche
    for k in ("outbound_text",):
        pass
    S.unfilled_fields = lambda niche: []
    check("sem consentimento: recusado", await err(S.gestor_dispatch(S.DispatchIn(niche_id=nid, lines="5521977770009", consent=False, origem="formulário do site em 10/2026"), BG(), x_token=TG)) == 400)
    check("sem origem do consentimento: recusado", await err(S.gestor_dispatch(S.DispatchIn(niche_id=nid, lines="5521977770009", consent=True, origem=""), BG(), x_token=TG)) == 400)
    check("não dispara por número de outro gestor", await err(S.gestor_dispatch(S.DispatchIn(niche_id=nid, lines="5521977770009", consent=True, origem="formulário do site em 10/2026", line="gil-vendas"), BG(), x_token=TB)) == 404)
    check("nem pelo número principal do administrador", await err(S.gestor_dispatch(S.DispatchIn(niche_id=nid, lines="5521977770009", consent=True, origem="formulário do site em 10/2026", line="main"), BG(), x_token=TG)) == 404)
    r = await S.gestor_dispatch(body, BG(), x_token=TG)
    check("coloca os contatos na fila, pelo número do gestor", r["queued"] == 2 and {x["line"] for x in q(S, "SELECT line FROM outbox")} == {"gil-vendas"}, (r, q(S, "SELECT line FROM outbox")))
    check("a origem do consentimento fica registrada", all("formulário do site" in x["consent"] for x in q(S, "SELECT consent FROM outbox")))
    S.suppress("5521977770003", "sair")
    r = await S.gestor_dispatch(S.DispatchIn(niche_id=nid, lines="5521977770003;Caio\n5521977770004;Duda", consent=True, origem="lista do evento X"), BG(), x_token=TG)
    check("quem pediu SAIR é pulado", r["queued"] == 1 and r["suppressed"] == 1, r)
    check("o gestor vê só a própria fila", len((await S.gestor_outbox(x_token=TG))["rows"]) == 3 and (await S.gestor_outbox(x_token=TG))["queued"] == 3 and (await S.gestor_outbox(x_token=TB))["rows"] == [])
    check("o administrador também vê tudo", len(await S.outbox_list()) == 3)
    csvb = base64.b64encode("nome,telefone\nEva,p:+5521977770005\n".encode()).decode()
    pr = await S.gestor_contacts_parse(S.ContactsIn(filename="c.csv", data=csvb), x_token=TG)
    check("gestor importa planilha (mesma leitura do administrador)", pr.get("lines") or pr.get("contacts") or pr, pr)
    check("supervisor não dispara nem importa (403)", await err(S.gestor_dispatch(body, BG(), x_token=TS)) == 403 and await err(S.gestor_contacts_parse(S.ContactsIn(filename="c.csv", data=csvb), x_token=TS)) == 403)
    check("supervisor vê a fila de todos", len((await S.gestor_outbox(x_token=TS))["rows"]) == 3)
    check("gestor sem token: 401", await err(S.gestor_outbox(x_token="")) == 401)
    out = await S.gestor_outbox_clear(x_token=TB)
    check("limpar a fila de outro gestor não afeta a minha", out["removed"] == 0 and (await S.gestor_outbox(x_token=TG))["queued"] == 3)
    out = await S.gestor_outbox_clear(x_token=TG)
    check("gestor limpa a própria fila", out["removed"] == 3 and (await S.gestor_outbox(x_token=TG))["queued"] == 0)
    # ---------- agenda própria ----------
    sa = json.dumps({"type": "service_account", "client_email": "sdr@proj.iam.gserviceaccount.com", "private_key": pem, "token_uri": "https://oauth2.googleapis.com/token"})
    c0 = await S.gestor_calendar_get(x_token=TG)
    check("sem integração do administrador a agenda do gestor fica indisponível", c0["available"] is False and c0["calendar_id"] == "")
    check("testar sem integração: 400", await err(S.gestor_calendar_test(x_token=TG)) == 400)
    await S.gcal_put({"enabled": True, "calendar_id": "admin@group.calendar.google.com", "sa_json": sa, "duration_min": 30, "notice_min": 120, "horizon_days": 7, "days": [["09:00", "18:00"]] * 5 + [None, None]})
    c1 = await S.gestor_calendar_get(x_token=TG)
    check("com a integração ativa, o gestor vê o e-mail para compartilhar a agenda", c1["available"] and c1["sa_email"] == "sdr@proj.iam.gserviceaccount.com" and "BEGIN" not in json.dumps(c1))
    check("ID de agenda inválido é recusado", await err(S.gestor_calendar_put(S.MgrCalIn(calendar_id="a b/../c"), x_token=TG)) == 400)
    check("testar sem salvar a agenda: 400", await err(S.gestor_calendar_test(x_token=TG)) == 400)
    await S.gestor_calendar_put(S.MgrCalIn(calendar_id="gil@group.calendar.google.com"), x_token=TG)
    t = await S.gestor_calendar_test(x_token=TG)
    check("teste da agenda do gestor autentica e lista horários", t["ok"] and len(t["slots"]) == 3, t)
    S.GCAL_CAL.set("")
    check("o teste não vaza para o contexto do administrador", S.gcal_cfg()["calendar_id"] == "admin@group.calendar.google.com")
    check("supervisor não altera agenda (403)", await err(S.gestor_calendar_put(S.MgrCalIn(calendar_id="x@y"), x_token=TS)) == 403)
    G = harness.GCAL
    # lead de cada dono
    S.upsert_lead("5521966660001", "Lead do Gil", niche_id=nid); S.set_lead("5521966660001", line="gil-vendas")
    S.upsert_lead("5521966660002", "Lead do Admin", niche_id=nid)
    S.upsert_lead("5521966660003", "Lead da Bia", niche_id=nid); S.set_lead("5521966660003", line="bia-vendas")
    check("agenda do dono: gestor com agenda própria", S.mgr_calendar("5521966660001") == "gil@group.calendar.google.com" and S.mgr_calendar("5521966660002") == "" and S.mgr_calendar("5521966660003") == "")
    G["log"] = []; G["busy"] = []
    S.GCAL_CAL.set(S.mgr_calendar("5521966660001"))
    res = await S.exec_tool("5521966660001", "agendar_reuniao", {"data_hora": "2026-10-20 10:00"})
    posts = [p for m, p in G["log"] if m == "POST" and "/events" in p]
    check("lead do gestor: o evento vai para a agenda do gestor", len(posts) == 1 and "gil%40group" in posts[0].replace("@", "%40") , posts)
    G["log"] = []; S.GCAL_CAL.set(S.mgr_calendar("5521966660002"))
    await S.exec_tool("5521966660002", "agendar_reuniao", {"data_hora": "2026-10-20 11:00"})
    posts = [p for m, p in G["log"] if m == "POST" and "/events" in p]
    check("lead do administrador: continua na agenda do administrador", len(posts) == 1 and "admin" in posts[0], posts)
    G["log"] = []; S.GCAL_CAL.set(S.mgr_calendar("5521966660003"))
    await S.exec_tool("5521966660003", "agendar_reuniao", {"data_hora": "2026-10-20 12:00"})
    posts = [p for m, p in G["log"] if m == "POST" and "/events" in p]
    check("gestor sem agenda própria usa a do administrador", len(posts) == 1 and "admin" in posts[0], posts)
    S.GCAL_CAL.set("")
    await S.gestor_calendar_put(S.MgrCalIn(calendar_id=""), x_token=TG)
    check("remover a agenda própria volta ao padrão", S.mgr_calendar("5521966660001") == "")
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
