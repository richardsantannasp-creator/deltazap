"""Auditoria: quem fez o quê, leitura de conversas, tentativas de login, escopo do gestor, exportação e LGPD."""
import asyncio, os, sys, tempfile, time, csv, io
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
async def main():
    S = harness.load_server(); S.PROVIDER = "qr"
    check("o middleware de auditoria está registrado", any(getattr(f, "__name__", "") == "audit_middleware" for f in harness.MIDDLEWARE))
    ADM = "testtoken"
    S.audit_request("POST", "/api/niches", ADM, 200, "10.0.0.1")
    S.audit_request("PUT", "/api/pacing", ADM, 200, "10.0.0.1")
    S.audit_request("DELETE", "/api/leads/5521999990001", ADM, 200, "10.0.0.1")
    S.audit_request("PUT", "/api/hours", ADM, 400, "10.0.0.1")
    S.audit_request("GET", "/api/leads", ADM, 200, "10.0.0.1")
    S.audit_request("POST", "/api/simulate", ADM, 200, "10.0.0.1")
    S.audit_request("POST", "/webhook", "", 200, "1.2.3.4")
    S.audit_request("POST", "/api/agent/login", "", 200, "1.2.3.4")
    rows = q(S, "SELECT * FROM audit ORDER BY id")
    acts = [r["action"] for r in rows]
    check("ações que mudam algo são registradas com texto legível", "Criou agente/nicho" in acts and "Alterou ritmo de envio" in acts, acts)
    check("o que é só leitura de lista, simulador e webhooks não entra", len(rows) == 4 and not any("simul" in a.lower() for a in acts), acts)
    check("quem fez: administrador, e de qual IP", all(r["actor"] == "administrador" and r["ip"] == "10.0.0.1" for r in rows))
    check("ação recusada fica marcada", any("recusada: 400" in a for a in acts), acts)
    d = next(r for r in rows if r["action"].startswith("Apagou"))
    check("apagar lead (LGPD) não guarda o número na auditoria", d["target"] == "(lead excluído)", d)
    check("o texto e o corpo das requisições não são guardados", not any(k in str(rows) for k in ("senha", "password", "text")))
    # atendentes e gestor
    await S.managers_add(S.ManagerIn(login="gil", name="Gil G", password="senhaforte1"))
    S._agent_create(S.AgentIn(login="rita", name="Rita", password="abcdef"), 0)
    S._agent_create(S.AgentIn(login="duda", name="Duda", password="abcdef"), 1)
    await err(S.agent_login(S.AgentLoginIn(login="rita", password="errada")))
    tr = (await S.agent_login(S.AgentLoginIn(login="rita", password="abcdef")))["token"]
    td = (await S.agent_login(S.AgentLoginIn(login="duda", password="abcdef")))["token"]
    tg = (await S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1")))["token"]
    S.upsert_lead("5521977770001", "Lia", niche_id=1)
    S.audit_request("POST", "/api/agent/send/5521977770001", tr, 200, "10.0.0.2")
    S.audit_request("POST", "/api/agent/send/5521977770001", td, 200, "10.0.0.3")
    S.audit_request("POST", "/api/gestor/agents", tg, 200, "10.0.0.4")
    S.audit_request("POST", "/api/agent/login", "", 401, "10.0.0.2")
    rows = q(S, "SELECT * FROM audit ORDER BY id")
    ent = [r for r in rows if r["action"] == "Entrou no painel"]
    check("entradas no painel e tentativa de login recusada são registradas", len(ent) == 3 and any(r["action"] == "Tentativa de login recusada" and r["target"] == "rita" for r in rows), [r["action"] for r in rows])
    rr = next(r for r in rows if r["action"] == "Respondeu o lead" and r["actor_name"] == "Rita")
    check("atendente: perfil, nome e lead alvo", rr["actor"] == "atendente" and rr["target"] == "5521977770001", rr)
    check("gestor: perfil e nome", any(r["actor"] == "gestor" and r["actor_name"] == "Gil G" and r["action"] == "Criou atendente" for r in rows))
    # leitura de conversa (uma vez por 30 min por pessoa)
    for _ in range(5): S.audit_request("GET", "/api/agent/messages/5521977770001", tr, 200, "10.0.0.2")
    S.audit_request("GET", "/api/gestor/messages/5521977770001", tg, 200, "10.0.0.4")
    S.audit_request("GET", "/api/messages/5521977770001", ADM, 200, "10.0.0.1")
    reads = q(S, "SELECT * FROM audit WHERE action='Leu a conversa'")
    check("leitura de conversa: 1 registro por pessoa (o painel consulta a cada 3 s)", len(reads) == 3 and {r["actor"] for r in reads} == {"atendente", "gestor", "administrador"}, reads)
    S.AUDIT_LAST.clear(); S.audit_request("GET", "/api/agent/messages/5521977770001", tr, 404, "10.0.0.2")
    check("leitura que falhou não conta", len(q(S, "SELECT * FROM audit WHERE action='Leu a conversa'")) == 3)
    S.audit_request("GET", "/api/leads", "token-errado", 401, "9.9.9.9"); S.audit_request("GET", "/api/leads", "token-errado", 401, "9.9.9.9")
    check("acesso negado é registrado uma vez por minuto por IP", len(q(S, "SELECT * FROM audit WHERE action LIKE 'Acesso negado%'")) == 1)
    # consulta, filtros, escopo, CSV
    r = await S.audit_list(days=30)
    check("administrador vê tudo, com os perfis para filtrar", len(r["rows"]) >= 12 and {"administrador", "atendente", "gestor"} <= set(r["actors"]), r["actors"])
    check("filtro por perfil", all(x["actor"] == "atendente" for x in (await S.audit_list(actor="atendente"))["rows"]))
    check("busca por texto", len((await S.audit_list(q="Respondeu"))["rows"]) == 2)
    g = await S.gestor_audit(x_token=tg)
    names = {x["actor_name"] for x in g["rows"]}
    check("gestor vê só as ações dele e da equipe dele (Duda), não as do administrador nem da Rita", "Gil G" in names and "Duda" in names and "Rita" not in names and "Administrador" not in names, names)
    check("gestor sem sessão não acessa a auditoria", await err(S.gestor_audit(x_token="")) == 401)
    resp = await S.audit_csv(days=30)
    raw = resp.body if hasattr(resp, "body") else resp.content
    body = raw if isinstance(raw, str) else raw.decode()
    rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
    check("CSV com cabeçalho e linhas", rows[0] == ["data_hora", "perfil", "pessoa", "acao", "alvo", "status", "ip"] and len(rows) > 10, rows[:2])
    # LGPD: apagar o lead anonimiza o alvo nos registros antigos
    S.audit_request("POST", "/api/leads/5521977770001/outcome", ADM, 200, "10.0.0.1")
    S.erase_lead("5521977770001")
    check("apagar o lead remove o número de todos os registros de auditoria", not q(S, "SELECT 1 FROM audit WHERE target='5521977770001'"))
    # retenção
    S.AUDIT_KEEP_DAYS = 1
    with S.conn() as c: c.execute("INSERT INTO audit(ts,actor,action) VALUES(?,?,?)", (time.time() - 5 * 86400, "administrador", "antiga"))
    import random; random.seed(1); real = random.random
    S.random.random = lambda: 0.0
    S.audit_add("administrador", 0, "x", "gatilho")
    check("registros além da retenção são apagados", not q(S, "SELECT 1 FROM audit WHERE action='antiga'"))
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
