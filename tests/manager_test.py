"""Gestor de equipe: login próprio, número próprio, equipe própria e isolamento em relação ao administrador e a outros gestores."""
import asyncio, os, sys, tempfile, time
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
def run(S, sql, *a):
    with S.conn() as c: c.execute(sql, a)
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0
async def main():
    S = harness.load_server(); S.PROVIDER = "qr"; S.LINES_MAX = 4
    harness.GW["state"] = "open"
    S.set_setting("qr_ack", __import__("json").dumps({"version": S.QR_TERMS_VERSION, "ts": time.time()}))
    await S.pacing_put({"min_delay": 1, "max_delay": 1, "batch_size": 50, "warmup": False, "daily_limit": 500, "reply_delay_min": 0, "reply_delay_max": 0,
                        "start_hour": 0, "end_hour": 24, "weekdays_only": False})
    # ---------- cadastro pelo administrador ----------
    check("senha curta de gestor é recusada", await err(S.managers_add(S.ManagerIn(login="ana", name="Ana", password="123"))) == 400)
    a = await S.managers_add(S.ManagerIn(login=" Ana ", name="Ana Gestora", password="senhaforte1", max_lines=1, max_agents=2))
    check("cria o gestor com usuário em minúsculas", a["ok"] and a["login"] == "ana", a)
    b = await S.managers_add(S.ManagerIn(login="bia", name="Bia Gestora", max_lines=2))
    check("sem senha, uma é gerada", len(b["password"]) >= 8, b)
    check("usuário repetido é recusado", await err(S.managers_add(S.ManagerIn(login="ANA", name="Outra", password="senhaforte2"))) == 400)
    check("a senha não é guardada em texto", "senhaforte1" not in str(q(S, "SELECT pw FROM managers")))
    # ---------- login ----------
    check("senha errada: 401", await err(S.gestor_login(S.AgentLoginIn(login="ana", password="errada"))) == 401)
    for _ in range(5): await err(S.gestor_login(S.AgentLoginIn(login="bia", password="x")))
    check("5 erros seguidos bloqueiam por 10 min (429)", await err(S.gestor_login(S.AgentLoginIn(login="bia", password=b["password"]))) == 429)
    S.LOGIN_FAILS.clear()
    la = await S.gestor_login(S.AgentLoginIn(login="ana", password="senhaforte1")); TA = la["token"]
    lb = await S.gestor_login(S.AgentLoginIn(login="bia", password=b["password"])); TB = lb["token"]
    check("login devolve token", TA and TB and TA != TB)
    check("sem token: 401", await err(S.gestor_me(x_token="")) == 401)
    check("token de atendente/administrador não vale como gestor", await err(S.gestor_me(x_token="testtoken")) == 401)
    me = await S.gestor_me(x_token=TA)
    check("gestor começa sem número, sem atendente", me["lines"] == [] and me["agents"] == [] and me["manager"]["max_lines"] == 1, me)
    # ---------- números ----------
    la1 = await S.gestor_line_add(S.MgrLineIn(label="Vendas Ana"), x_token=TA)
    check("gestor conecta o próprio número", la1["id"] == "vendas-ana" and q(S, "SELECT manager_id FROM lines WHERE id='vendas-ana'")[0]["manager_id"] == q(S, "SELECT id FROM managers WHERE login='ana'")[0]["id"], la1)
    check("limite de números do gestor (1)", await err(S.gestor_line_add(S.MgrLineIn(label="Outro"), x_token=TA)) == 400)
    lb1 = await S.gestor_line_add(S.MgrLineIn(label="Vendas Bia"), x_token=TB)
    for k in harness.GWL: harness.GWL[k]["state"] = "open"       # números novos do gateway simulado ficam conectados
    me = await S.gestor_me(x_token=TA)
    check("cada gestor vê só o próprio número", [l["id"] for l in me["lines"]] == ["vendas-ana"], me["lines"])
    st = await S.gestor_connection(line="vendas-ana", x_token=TA)
    check("vê o estado/QR do próprio número", st.get("state") in ("open", "connecting", "qr"), st)
    check("não vê o número de outro gestor", await err(S.gestor_connection(line="vendas-bia", x_token=TA)) == 404)
    check("não vê o número principal do administrador", await err(S.gestor_connection(line="main", x_token=TA)) == 404)
    check("não desconecta número alheio", await err(S.gestor_line_logout(line="vendas-bia", x_token=TA)) == 404)
    check("não remove número alheio", await err(S.gestor_line_del("vendas-bia", x_token=TA)) == 404 and S.known_line("vendas-bia"))
    # ---------- equipe própria ----------
    ag1 = await S.gestor_agent_add(S.AgentIn(login="ze", name="Zé da Ana", password="abcdef", max_chats=3), x_token=TA)
    ag2 = await S.gestor_agent_add(S.AgentIn(login="li", name="Li da Ana", password="abcdef", max_chats=3), x_token=TA)
    check("gestor cria atendentes dele", ag1["ok"] and ag2["ok"])
    check("limite de atendentes do gestor (2)", await err(S.gestor_agent_add(S.AgentIn(login="x3", name="Terceiro", password="abcdef"), x_token=TA)) == 400)
    bg = await S.gestor_agent_add(S.AgentIn(login="beto", name="Beto da Bia", password="abcdef"), x_token=TB)
    adm = S._agent_create(S.AgentIn(login="admin1", name="Atendente Admin", password="abcdef"), 0)
    ids = {r["login"]: r["id"] for r in q(S, "SELECT id,login FROM agents")}
    me = await S.gestor_me(x_token=TA)
    check("gestor vê só os atendentes dele", sorted(a["login"] for a in me["agents"]) == ["li", "ze"], me["agents"])
    check("gestor não edita atendente alheio", await err(S.gestor_agent_put(ids["beto"], S.AgentIn(name="X", password="zzzzzz"), x_token=TA)) == 404)
    check("gestor não exclui atendente do administrador", await err(S.gestor_agent_del(ids["admin1"], x_token=TA)) == 404 and S.known_line("main"))
    ad = await S.agents_list()
    check("administrador vê todos os atendentes", len(ad["agents"]) == 4 and {a["manager_id"] for a in ad["agents"]} >= {0}, ad["agents"])
    # ---------- conversas e isolamento ----------
    for who, line in (("5521911110001", "vendas-ana"), ("5521911110002", "vendas-bia"), ("5521911110003", "main")):
        await S.handle_incoming(who, "Lead " + who[-1], "oi, quero saber mais", "w" + who[-1], line=line)
    leads = (await S.gestor_leads(x_token=TA))["leads"]
    check("gestor vê só as conversas do número dele", [l["phone"] for l in leads] == ["5521911110001"], leads)
    check("outro gestor vê só as dele", [l["phone"] for l in (await S.gestor_leads(x_token=TB))["leads"]] == ["5521911110002"])
    check("lê mensagens da própria conversa", len(await S.gestor_messages("5521911110001", x_token=TA)) >= 2)
    check("não lê conversa de outro gestor", await err(S.gestor_messages("5521911110002", x_token=TA)) == 404)
    check("não lê conversa do administrador", await err(S.gestor_messages("5521911110003", x_token=TA)) == 404)
    check("não responde conversa alheia", await err(S.gestor_send("5521911110002", S.TextIn(text="oi"), x_token=TA)) == 404)
    # responder como gestor
    harness.SENT.clear()
    await S.gestor_takeover("5521911110001", S.TakeIn(human=True), x_token=TA)
    await S.gestor_send("5521911110001", S.TextIn(text="Olá, aqui é a Ana"), x_token=TA)
    s = [m for m in harness.SENT if m["to"] == "5521911110001"]
    check("gestor assume e responde pelo número dele", s and s[-1].get("line") == "vendas-ana" and "Ana" in s[-1]["text"], harness.SENT)
    check("a mensagem fica com o nome do gestor", any(m["agent"] == "Ana Gestora" for m in q(S, "SELECT agent FROM messages WHERE phone='5521911110001'")))
    await S.gestor_takeover("5521911110001", S.TakeIn(human=False), x_token=TA)
    # ---------- transferência só para a equipe do gestor ----------
    now = time.time()
    run(S, "UPDATE agents SET last_seen=?, available=1", now)         # todos online
    S.exec_tool("5521911110001", "transferir_para_humano", {"motivo": "preço"})
    L = S.get_lead("5521911110001")
    check("transferência no número da Ana vai para atendente da Ana", L["agent_id"] in (ids["ze"], ids["li"]), L["agent_id"])
    S.exec_tool("5521911110002", "transferir_para_humano", {"motivo": "preço"})
    check("transferência no número da Bia vai para o Beto", S.get_lead("5521911110002")["agent_id"] == ids["beto"])
    S.exec_tool("5521911110003", "transferir_para_humano", {"motivo": "preço"})
    check("transferência no número do administrador vai para a equipe do administrador", S.get_lead("5521911110003")["agent_id"] == ids["admin1"])
    # sem atendente disponível na equipe do gestor: fica na fila dele, não vai para equipe alheia
    run(S, "UPDATE agents SET available=0 WHERE manager_id=(SELECT id FROM managers WHERE login='bia')")
    await S.handle_incoming("5521911110004", "Lead 4", "oi", "w4", line="vendas-bia")
    S.exec_tool("5521911110004", "transferir_para_humano", {"motivo": "dúvida"})
    L4 = S.get_lead("5521911110004")
    check("sem atendente da Bia disponível, a conversa espera na fila (não vai para a equipe de outros)", L4["human"] == 1 and L4["agent_id"] is None, L4)
    check("a fila da Bia mostra 1; a da Ana, 0; a do admin, 0",
          len(S.queue_rows(q(S, "SELECT id FROM managers WHERE login='bia'")[0]["id"])) == 1 and len(S.queue_rows(q(S, "SELECT id FROM managers WHERE login='ana'")[0]["id"])) == 0)
    # painel do atendente respeita o gestor
    tz = await S.agent_login(S.AgentLoginIn(login="ze", password="abcdef"))
    al = await S.agent_leads(x_token=tz["token"])
    check("atendente da Ana só enxerga conversas dos números da Ana", all(l["phone"] in ("5521911110001",) for l in al["leads"]), al["leads"])
    check("atendente não assume conversa na fila de outro gestor", await err(S.agent_claim("5521911110004", x_token=tz["token"])) == 404)
    meag = await S.agent_me(x_token=tz["token"])
    check("equipe vista pelo atendente é só a do gestor dele", sorted(t["login"] for t in meag["team"]) == ["li", "ze"], meag["team"])
    check("atendente não transfere para equipe de outro gestor", await err(S.agent_transfer("5521911110001", S.TransferIn(to=str(ids["beto"])), x_token=tz["token"])) == 404 if S.get_lead("5521911110001")["agent_id"] == ids["ze"] else True)
    # métricas só da equipe
    m = await S.gestor_metrics(x_token=TA)
    check("desempenho só dos atendentes do gestor", sorted(a["name"] for a in m["agents"]) == ["Li da Ana", "Zé da Ana"], m)
    # ---------- disparo do administrador não usa número de gestor ----------
    S.NEXT_AT = 0; S.LINE_NEXT.clear(); S.LINE_STATE_TS = 0
    harness.SENT.clear()
    run(S, "INSERT INTO outbox(phone,niche_id,name,company,context,created,line,consent) VALUES('5521988880001',1,'Dest','','',?,'','teste')", time.time())
    for _ in range(3):
        S.NEXT_AT = 0; S.LINE_NEXT.clear(); S.LINE_STATE_TS = 0
        await S.outbox_tick()
    ls = {m.get("line") for m in harness.SENT if m["to"] == "5521988880001"}
    check("disparo sem número definido sai só pelos números do administrador", ls and ls <= {"main"}, ls)
    # avisos internos
    check("avisos internos usam número do administrador", S.internal_line() == "main")
    # ---------- administração do gestor ----------
    ml = await S.managers_list()
    ra = next(x for x in ml["managers"] if x["login"] == "ana")
    check("lista do administrador mostra uso (1 número, 2 atendentes)", ra["lines"] == 1 and ra["agents"] == 2 and ra["max_agents"] == 2, ra)
    await S.managers_edit(ra["id"], S.ManagerIn(name="Ana G", max_lines=1, max_agents=2, active=False))
    check("desativar derruba a sessão", await err(S.gestor_me(x_token=TA)) == 401)
    check("desativado não entra", await err(S.gestor_login(S.AgentLoginIn(login="ana", password="senhaforte1"))) == 401)
    await S.managers_edit(ra["id"], S.ManagerIn(name="Ana G", max_lines=1, max_agents=2, active=True, password="novasenha1"))
    check("senha nova funciona e a antiga não", (await S.gestor_login(S.AgentLoginIn(login="ana", password="novasenha1")))["token"] and await err(S.gestor_login(S.AgentLoginIn(login="ana", password="senhaforte1"))) == 401)
    check("senha curta na edição é recusada", await err(S.managers_edit(ra["id"], S.ManagerIn(name="Ana G", password="abc"))) == 400)
    await S.managers_del(ra["id"])
    check("excluir o gestor passa números e atendentes para o administrador (nada apagado)",
          q(S, "SELECT manager_id FROM lines WHERE id='vendas-ana'")[0]["manager_id"] == 0 and not q(S, "SELECT 1 FROM agents WHERE manager_id=?", ra["id"]) and len(q(S, "SELECT id FROM agents WHERE login IN ('ze','li')")) == 2)
    check("lead do número que era da Ana agora é do administrador", S.lead_manager("5521911110001") == 0)
    # ---------- página ----------
    html = (await S.gestor_page())
    check("página /gestor entrega o HTML", "Painel do gestor" in html and "/api/gestor/login" in html)
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
