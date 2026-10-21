"""Transferência para atendente humano logado: login, presença, fila, distribuição, assumir/transferir/devolver, permissões."""
import asyncio, os, sys, tempfile, time, json
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
    S = harness.load_server(); S.PROVIDER = "qr"
    mk = lambda ph, nm: S.upsert_lead(ph, nm, niche_id=1, origin="receptivo")
    L = {k: f"55119888800{i:02d}" for i, k in enumerate("abcdefgh")}
    for k, ph in L.items(): mk(ph, k.upper() * 3)
    tool = lambda ph, why="quer falar com pessoa": S.exec_tool(ph, "transferir_para_humano", {"motivo": why})

    # ---- sem atendentes cadastrados: comportamento de antes ----
    t = tool(L["a"])
    check("sem atendentes: transferência funciona como antes (IA pausa)", "uma pessoa vai assumir" in t and S.get_lead(L["a"])["human"] == 1)

    # ---- cadastro e login ----
    r = await S.agents_add(S.AgentIn(name="Ana Lima", login=" Ana@Loja.com ", password="", max_chats=2))
    check("criar atendente gera senha e guarda só o hash", len(r["password"]) >= 8 and r["password"] not in q(S, "SELECT pw FROM agents")[0]["pw"] and q(S, "SELECT pw FROM agents")[0]["pw"].startswith("pbkdf2$"))
    check("usuário duplicado e senha curta são recusados", await code(S.agents_add(S.AgentIn(name="X", login="ana@loja.com", password="123456"))) == 400
          and await code(S.agents_add(S.AgentIn(name="X", login="novo", password="123"))) == 400)
    b = await S.agents_add(S.AgentIn(name="Bruno Reis", login="bruno", password="senha-do-bruno", max_chats=2))
    check("senha errada: 401; sem usuário: 401", await code(S.agent_login(S.AgentLoginIn(login="bruno", password="errada"))) == 401 and await code(S.agent_login(S.AgentLoginIn(login="ninguem", password="x"))) == 401)
    for _ in range(4): await code(S.agent_login(S.AgentLoginIn(login="bruno", password="errada")))
    check("5 erros seguidos bloqueiam o login por um tempo (429)", await code(S.agent_login(S.AgentLoginIn(login="bruno", password="senha-do-bruno"))) == 429)
    S.LOGIN_FAILS.clear()
    la = await S.agent_login(S.AgentLoginIn(login="ANA@loja.com", password=r["password"]))
    ta = la["token"]; ida = la["agent"]["id"]
    check("login (sem diferenciar maiúsculas) devolve sessão e atendente disponível", ta and la["agent"]["online"] and la["agent"]["name"] == "Ana Lima")
    check("sessão inválida é recusada", await code(S.agent_me(x_token="lixo")) == 401 and await code(S.agent_me(x_token="")) == 401)

    # ---- transferência: fila x atribuição ----
    mk(L["b"], "Beto"); 
    t = tool(L["b"])
    lb = S.get_lead(L["b"])
    check("com atendente online: conversa vai para ele e a IA recebe o nome para avisar o lead", lb["agent_id"] == ida and "Ana Lima" in t and lb["human"] == 1 and lb["stage"] == "humano", t)
    S.exec_tool(L["c"], "transferir_para_humano", {"motivo": "reclamação"})
    S.exec_tool(L["d"], "transferir_para_humano", {"motivo": "preço"})
    lc, ld = S.get_lead(L["c"]), S.get_lead(L["d"])
    check("a conversa que já esperava na fila foi entregue ao entrar o 1º atendente", S.get_lead(L["a"])["agent_id"] == ida)
    check("limite de conversas por atendente (2): as seguintes ficam na fila", lc["agent_id"] is None and ld["agent_id"] is None and ld["human"] == 1, (lc["agent_id"], ld["agent_id"]))
    check("a IA é orientada a ser honesta quando a fila está sem ninguém", "ninguém está disponível" in S.exec_tool(L["e"], "transferir_para_humano", {"motivo": "x"}) and "prazo" in S.exec_tool(L["f"], "transferir_para_humano", {"motivo": "x"}))
    check("o motivo da transferência fica guardado", S.get_lead(L["b"])["handoff_reason"] == "quer falar com pessoa")

    # ---- o que o atendente enxerga e pode fazer ----
    lst = (await S.agent_leads(x_token=ta))["leads"]
    got = {x["phone"] for x in lst}
    check("lista do atendente = as dele + a fila (não vê conversas de outros nem de lead sem transferência)", L["b"] in got and L["d"] in got and L["g"] not in got and L["a"] in got, got)
    S.add_msg(L["b"], "lead", "oi, cadê o orçamento?"); S.add_msg(L["b"], "lead", "alguém?")
    me = [x for x in (await S.agent_leads(x_token=ta))["leads"] if x["phone"] == L["b"]][0]
    check("mensagens do lead sem resposta contam como não lidas", me["unread"] == 2, me["unread"])
    check("na fila ele pode ler antes de assumir, mas não responder", len(await S.agent_messages(L["d"], x_token=ta)) >= 0 and await code(S.agent_send(L["d"], S.TextIn2(text="oi"), x_token=ta)) == 403)
    check("conversa de lead que ninguém transferiu é negada", await code(S.agent_messages(L["g"], x_token=ta)) == 403)
    harness.SENT.clear()
    await S.agent_send(L["b"], S.TextIn2(text="Olá, aqui é a Ana. Já te mando o orçamento."), x_token=ta)
    m = q(S, "SELECT role,agent,text FROM messages WHERE phone=? ORDER BY id DESC LIMIT 1", L["b"])[0]
    check("resposta do atendente vai ao WhatsApp e fica registrada com o nome dele", m["role"] == "humano" and m["agent"] == "Ana Lima" and any(s["to"] == L["b"] and "Ana" in s["text"] for s in harness.SENT), (m, harness.SENT))
    me = [x for x in (await S.agent_leads(x_token=ta))["leads"] if x["phone"] == L["b"]][0]
    check("responder zera o contador de não lidas", me["unread"] == 0)
    adm = [x for x in await S.leads() if x["phone"] == L["b"]][0]
    check("painel do administrador mostra quem atende", adm["agent_name"] == "Ana Lima")
    check("histórico do administrador traz o autor das mensagens", (await S.msgs(L["b"]))[-1]["agent"] == "Ana Lima")

    # ---- segundo atendente, disputa e distribuição ----
    lb2 = await S.agent_login(S.AgentLoginIn(login="bruno", password="senha-do-bruno")); tb = lb2["token"]; idb = lb2["agent"]["id"]
    await S.handoff_sweep()
    check("quando entra alguém, a fila é entregue (sweep)", S.get_lead(L["d"])["agent_id"] == idb or S.get_lead(L["e"])["agent_id"] == idb)
    q_left = [x["phone"] for x in S.queue_rows()]
    for ph in q_left: S.handoff_begin(ph, "volta")  # só garante que não quebra repetir
    check("assumir uma conversa que outro já pegou: 409", await code(S.agent_claim(L["b"], x_token=tb)) == 409)
    mk(L["h"], "Hugo"); S.set_lead(L["h"], human=1, stage="humano", agent_id=None, handoff_at=time.time())
    S.hand_cfg(); S.set_setting("handoff", json.dumps({**S.hand_cfg(), "auto_assign": False}))
    check("distribuição automática desligada: fica na fila", S.assign_next(L["h"]) is None)
    check("atendente assume pela fila", (await S.agent_claim(L["h"], x_token=tb))["ok"] and S.get_lead(L["h"])["agent_id"] == idb)
    S.set_setting("handoff", json.dumps({**S.hand_cfg(), "auto_assign": True}))

    # ---- ausência / sumiço ----
    await S.agent_status(S.AgentStatusIn(available=False), x_token=tb)
    mk("5511988889999", "Zeca"); S.set_lead("5511988889999", human=1, stage="humano", agent_id=None, handoff_at=time.time())
    n = len([1 for x in q(S, "SELECT agent_id FROM leads WHERE phone='5511988889999'") if x["agent_id"] is None])
    check("atendente ausente não recebe conversa nova", S.assign_next("5511988889999", exclude=(ida,)) is None and n == 1)
    with S.conn() as c: c.execute("UPDATE agents SET last_seen=? WHERE id=?", (time.time() - 3600, ida))
    before = q(S, "SELECT COUNT(*) n FROM leads WHERE agent_id=? AND human=1 AND outcome=''", ida)[0]["n"]
    await S.handoff_sweep()
    after = q(S, "SELECT COUNT(*) n FROM leads WHERE agent_id=? AND human=1 AND outcome=''", ida)[0]["n"]
    check("atendente que sumiu há muito tempo: as conversas voltam para a fila", before > 0 and after == 0, (before, after))
    await S.agent_status(S.AgentStatusIn(available=True), x_token=tb)
    check("ao ficar disponível, ele fica no limite (2; assumir à mão pode passar) e o resto espera", S.agent_load(idb) >= 2 and len(S.queue_rows()) >= 1, (S.agent_load(idb), len(S.queue_rows())))

    # ---- prazo da fila com IA de volta ----
    S.set_setting("handoff", json.dumps({**S.hand_cfg(), "fallback": "ia", "wait_min": 1}))
    mk("5511988887777", "Nina")
    with S.conn() as c:
        c.execute("UPDATE agents SET available=0"); 
    S.set_lead("5511988887777", human=1, stage="humano", agent_id=None, handoff_at=time.time() - 600)
    harness.SENT.clear(); await S.handoff_sweep()
    nl = S.get_lead("5511988887777")
    check("fila vencida com 'IA volta': IA retoma e avisa o lead com honestidade", nl["human"] == 0 and any(s["to"] == "5511988887777" and "equipe" in s["text"] for s in harness.SENT), (nl["human"], harness.SENT))
    with S.conn() as c: c.execute("UPDATE agents SET available=1")

    # ---- devolver, transferir, resultado ----
    ph = L["h"]
    r1 = await S.agent_transfer(ph, S.TransferIn(to=str(ida)), x_token=tb)
    check("transferir direto para colega", S.get_lead(ph)["agent_id"] == ida)
    with S.conn() as c: c.execute("UPDATE agents SET last_seen=? WHERE id IN (?,?)", (time.time(), ida, idb))
    await S.agent_transfer(ph, S.TransferIn(to="fila"), x_token=ta)
    check("devolver à fila reentrega a outro (não volta para quem devolveu)", S.get_lead(ph)["agent_id"] in (idb, None) and S.get_lead(ph)["agent_id"] != ida)
    own = S.get_lead(ph)["agent_id"]; tk = tb if own == idb else None
    if tk:
        await S.agent_release(ph, x_token=tk)
        lh = S.get_lead(ph)
        check("devolver à IA: IA volta a atender, sem atendente", lh["human"] == 0 and lh["agent_id"] is None and lh["stage"] == "qualificando")
    ph2 = L["c"]
    if S.get_lead(ph2)["agent_id"] != ida: S.set_lead(ph2, agent_id=ida)
    await S.agent_outcome(ph2, S.OutcomeIn(outcome="ganho", reason=""), x_token=ta)
    check("resultado marcado pelo atendente fecha o lead e libera a vaga dele", S.get_lead(ph2)["outcome"] == "ganho" and S.agent_load(ida) < 3)

    # ---- administração ----
    S.set_lead(L["g"], human=0)
    await S.takeover(L["g"], S.TakeIn(human=True))
    check("administrador que assume pelo painel fica como 'painel' e não entra na fila", S.get_lead(L["g"])["agent_id"] == -1 and L["g"] not in [x["phone"] for x in S.queue_rows()])
    await S.takeover(L["g"], S.TakeIn(human=False))
    check("retomar a IA limpa o responsável", S.get_lead(L["g"])["agent_id"] is None and S.get_lead(L["g"])["human"] == 0)
    await S.lead_handoff(L["g"])
    check("'Enviar à equipe' do painel coloca na fila/entrega", S.get_lead(L["g"])["human"] == 1)
    lst = await S.agents_list()
    check("painel lista atendentes com presença e carga", len(lst["agents"]) == 2 and "load" in lst["agents"][0] and "config" in lst)
    await S.agents_edit(ida, S.AgentIn(name="Ana Lima", max_chats=2, active=False))
    check("desativar: sessão cai e conversas dela voltam à fila", await code(S.agent_me(x_token=ta)) == 401 and S.agent_load(ida) == 0)
    check("atendente desativado não consegue entrar", await code(S.agent_login(S.AgentLoginIn(login="ana@loja.com", password=r["password"]))) == 401)
    await S.agents_edit(idb, S.AgentIn(name="Bruno Reis", max_chats=2, active=True, password="outra-senha-1"))
    check("trocar a senha derruba as sessões abertas", await code(S.agent_me(x_token=tb)) == 401 and (await S.agent_login(S.AgentLoginIn(login="bruno", password="outra-senha-1")))["token"])
    await S.agents_del(idb)
    check("excluir atendente remove o acesso", len(q(S, "SELECT 1 FROM agents WHERE id=?", idb)) == 0)
    cfg = await S.handoff_put({"fallback": "ia", "wait_min": "30", "reassign_min": 99999, "auto_assign": False})
    check("regras da fila: salvar valida e limita", cfg["fallback"] == "ia" and cfg["wait_min"] == 30 and cfg["reassign_min"] == 1440 and cfg["auto_assign"] is False)
    check("página /atendente é servida", "Painel do atendente" in await S.atendente_page())
    await S.agents_add(S.AgentIn(name="Caio", login="caio", password="caio-123456"))
    tc = (await S.agent_login(S.AgentLoginIn(login="caio", password="caio-123456")))["token"]
    await S.agent_logout(x_token=tc)
    check("sair encerra a sessão e deixa o atendente ausente", await code(S.agent_me(x_token=tc)) == 401 and q(S, "SELECT available FROM agents WHERE login='caio'")[0]["available"] == 0)
    print(f"\n{OK} ok, {FAIL} falha(s)"); sys.exit(1 if FAIL else 0)
asyncio.run(main())
