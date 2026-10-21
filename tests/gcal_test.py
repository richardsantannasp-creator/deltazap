"""Google Agenda: conta de serviço (JWT RS256), horários livres, criação/remarcação do evento, erros e segurança."""
import asyncio, os, sys, tempfile, json
from datetime import datetime, timedelta
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
async def code(coro):
    try: await coro; return 200
    except Exception as e: return getattr(e, "status_code", 500)
async def main():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    harness.GCAL["pub"] = key.public_key()
    S = harness.load_server(); S.PROVIDER = "qr"
    TZ = S.TZ
    seg = datetime(2026, 10, 19, 8, 0, tzinfo=TZ)           # segunda 08:00 (relógio congelado)
    S.now_local = lambda: seg
    sa = json.dumps({"type": "service_account", "client_email": "sdr@proj.iam.gserviceaccount.com", "private_key": pem, "token_uri": "https://oauth2.googleapis.com/token"})
    nid = S.default_niche_id(); G = harness.GCAL
    S.upsert_lead("5521955550001", "Carla Souza", niche_id=nid)
    check("desligado: agendar_reuniao funciona como antes e a ferramenta de horários não aparece", S.exec_tool("5521955550001", "agendar_reuniao", {"data_hora": "2026-10-20 10:00"}).startswith("Agendado para") and not any(t["name"] == "consultar_horarios" for t in S.tools_for(S.get_niche(nid))))
    S.upsert_lead("5521955550001", "Carla Souza", niche_id=nid); S.set_lead("5521955550001", stage="qualificando", meeting="")
    # configuração
    check("ligar sem agenda/credencial é recusado", await code(S.gcal_put({"enabled": True, "calendar_id": ""})) == 400 and await code(S.gcal_put({"enabled": True, "calendar_id": "x@group.calendar.google.com"})) == 400)
    check("JSON inválido / sem chave / token_uri estranho são recusados",
          await code(S.gcal_put({"sa_json": "{nao"})) == 400 and await code(S.gcal_put({"sa_json": '{"client_email":"a@b"}'})) == 400
          and await code(S.gcal_put({"sa_json": json.dumps({"client_email": "a@b", "private_key": pem, "token_uri": "https://evil.example/token"})})) == 400)
    r = await S.gcal_put({"enabled": True, "calendar_id": "vendas@group.calendar.google.com", "sa_json": sa, "duration_min": 30, "notice_min": 120, "horizon_days": 7,
                          "days": [["09:00", "12:00"]] * 5 + [None, None]})
    check("salva e fica pronto", r["ready"])
    g = await S.gcal_get()
    check("a chave privada NUNCA volta para a tela (só o e-mail)", "BEGIN" not in json.dumps(g) and g["sa_email"] == "sdr@proj.iam.gserviceaccount.com" and g["has_sa"])
    check("o servidor guarda só e-mail e chave (nada de token_uri extra)", set(json.loads(S.get_setting("gcal_sa"))) == {"client_email", "private_key"})
    t = await S.gcal_test()
    check("teste de conexão: autentica com JWT RS256 válido e lista horários", t["ok"] and t["calendar"] == "Comercial" and len(t["slots"]) == 3 and G["tokens"] == 1, t)
    check("a ferramenta de horários aparece e o agente é orientado a usá-la", any(x["name"] == "consultar_horarios" for x in S.tools_for(S.get_niche(nid))) and "consultar_horarios" in json.dumps(S.build_system(S.get_lead("5521955550001"), S.get_niche(nid), "x"), ensure_ascii=False, default=str))
    # horários livres
    G["busy"] = [("2026-10-19T09:00:00-03:00", "2026-10-19T10:30:00-03:00")]
    out = await S.consultar_horarios("5521955550001", {})
    check("só mostra horários dentro do expediente, após a antecedência e fora dos ocupados", "2026-10-19 10:30" in out and "2026-10-19 09:00" not in out and "2026-10-19 10:00" not in out and "13:00" not in out, out)
    check("antecedência mínima: segunda 08:00 + 2 h = nada antes das 10:00", "2026-10-19 09:30" not in out)
    check("variedade: no máximo 3 por dia", out.count("2026-10-19") <= 3 and "2026-10-20" in out, out)
    check("token reaproveitado (uma só autenticação)", G["tokens"] == 1)
    # agendar
    ph = "5521955550001"
    res = await S.exec_tool(ph, "agendar_reuniao", {"data_hora": "2026-10-20 10:00"})
    ev = list(G["events"].values())
    lead = S.get_lead(ph)
    check("cria o evento na agenda com horário, fuso, nome e telefone", len(ev) == 1 and ev[0]["start"]["dateTime"].startswith("2026-10-20T10:00") and ev[0]["end"]["dateTime"].startswith("2026-10-20T10:30") and ev[0]["start"]["timeZone"] == str(TZ) and "Carla Souza" in ev[0]["summary"] and "5521955550001" in ev[0]["description"], ev)
    check("lead vira reuniao_agendada, guarda o id do evento e a IA recebe confirmação", lead["stage"] == "reuniao_agendada" and lead["meeting_event"] == "ev1" and "confirmado na agenda" in res, (lead["stage"], res))
    # remarcar
    res = await S.exec_tool(ph, "agendar_reuniao", {"data_hora": "2026-10-21 11:00"})
    check("remarcar apaga o evento antigo e cria o novo", list(G["events"]) == ["ev2"] and S.get_lead(ph)["meeting_event"] == "ev2", list(G["events"]))
    # indisponível
    S.upsert_lead("5521955550002", "Dani", niche_id=nid); G["busy"] = [("2026-10-22T09:00:00-03:00", "2026-10-22T10:00:00-03:00")]
    n0 = len(G["events"])
    res = await S.exec_tool("5521955550002", "agendar_reuniao", {"data_hora": "2026-10-22 09:30"})
    check("horário ocupado: não cria evento, não muda o estágio e oferece alternativas", len(G["events"]) == n0 and S.get_lead("5521955550002")["stage"] != "reuniao_agendada" and "NÃO confirme" in res and "- " in res, res)
    res = await S.exec_tool("5521955550002", "agendar_reuniao", {"data_hora": "2026-10-24 10:00"})
    check("sábado (fora do expediente): recusado", len(G["events"]) == n0 and "não está disponível" in res, res)
    res = await S.exec_tool("5521955550002", "agendar_reuniao", {"data_hora": "2026-10-19 09:00"})
    check("muito próximo (antecedência): recusado", len(G["events"]) == n0 and "não está disponível" in res)
    res = await S.exec_tool("5521955550002", "agendar_reuniao", {"data_hora": "amanhã cedo"})
    check("formato inválido: orienta o agente", "Formato inválido" in res and len(G["events"]) == n0)
    # lead de teste
    S.upsert_lead("5521955550003", "Teste", niche_id=nid, test=1)
    res = await S.exec_tool("5521955550003", "agendar_reuniao", {"data_hora": "2026-10-20 09:00"})
    check("lead de teste não escreve na agenda real", len(G["events"]) == n0 and "Agendado" in res)
    # falhas
    G["busy"] = []; S.upsert_lead("5521955550004", "Edu", niche_id=nid); G["fail_create"] = 1
    res = await S.exec_tool("5521955550004", "agendar_reuniao", {"data_hora": "2026-10-20 09:30"}); G["fail_create"] = 0
    check("Google fora do ar: registra a reunião localmente e avisa que a equipe confirma", S.get_lead("5521955550004")["stage"] == "reuniao_agendada" and "equipe confirma" in res and not S.get_lead("5521955550004")["meeting_event"], res)
    G["forbidden"] = 1
    out = await S.consultar_horarios("5521955550004", {}); G["forbidden"] = 0
    check("agenda não compartilhada: o agente é orientado a combinar sem travar", "Não consegui consultar" in out)
    t = await S.gcal_test() if False else None
    G["forbidden"] = 1; t = await S.gcal_test(); G["forbidden"] = 0
    check("teste mostra a instrução de compartilhar com o e-mail da conta de serviço", not t["ok"] and "sdr@proj.iam.gserviceaccount.com" in t["error"], t)
    S.GCAL_TOK.update(tok=None, exp=0); G["token_fail"] = 1
    t = await S.gcal_test(); G["token_fail"] = 0
    check("credencial recusada pelo Google: erro claro", not t["ok"] and "recusou" in t["error"], t)
    # token expirado (401) renova sozinho
    S.GCAL_TOK.update(tok="velho", exp=9e12)
    out = await S.consultar_horarios("5521955550004", {})
    check("token inválido (401): renova e repete a chamada", "Horários livres" in out, out)
    # diagnóstico
    d = await S.run_diagnostics()
    ag = next((c for c in d["checks"] if c["id"] == "agenda"), None)
    check("diagnóstico confere o Google Agenda", ag and ag["status"] == "ok", ag)
    # remover credencial
    await S.gcal_put({"enabled": False, "calendar_id": "vendas@group.calendar.google.com", "remove_sa": True})
    check("remover a conta de serviço desliga o uso", not S.gcal_ready() and not any(t["name"] == "consultar_horarios" for t in S.tools_for(S.get_niche(nid))))
    print(f"\n{OK} ok, {FAIL} falha(s)"); sys.exit(1 if FAIL else 0)
asyncio.run(main())
