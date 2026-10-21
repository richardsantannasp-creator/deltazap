"""Equipe: horário de atendimento, respostas rápidas, notas internas, métricas por atendente."""
import asyncio, os, sys, tempfile, time, json
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
async def code(coro):
    try: await coro; return 200
    except Exception as e: return getattr(e, "status_code", 500)
async def main():
    S = harness.load_server(); S.PROVIDER = "qr"; harness.GW["state"] = "open"
    TZ = S.TZ
    seg_10 = datetime(2026, 10, 19, 10, 0, tzinfo=TZ)     # segunda
    seg_20 = datetime(2026, 10, 19, 20, 0, tzinfo=TZ)
    sab_10 = datetime(2026, 10, 24, 10, 0, tzinfo=TZ)
    # ---- horário
    check("desligado: sempre dentro do horário", S.in_hours(seg_20))
    e = await code(S.hours_put({"enabled": True, "days": [None] * 7}))
    check("ligar sem nenhum dia definido é recusado", e == 400)
    r = await S.hours_put({"enabled": True, "days": [["09:00", "18:00"]] * 5 + [["09:00", "12:00"], None], "message": "Voltamos {volta}. Horário: {horario}"})
    check("salva a configuração", r["ok"])
    check("segunda 10h: aberto; 20h: fechado; sábado 10h: aberto; domingo: fechado", S.in_hours(seg_10) and not S.in_hours(seg_20) and S.in_hours(sab_10) and not S.in_hours(datetime(2026, 10, 25, 10, tzinfo=TZ)))
    check("texto do horário agrupa os dias", "de segunda a sexta, das 09:00 às 18:00" in S.hours_text() and "sábado, das 09:00 às 12:00" in S.hours_text(), S.hours_text())
    n = S.next_open(seg_20)
    check("próxima abertura: terça 09:00", n.weekday() == 1 and n.hour == 9, n)
    check("sexta à noite: próxima abertura é sábado de manhã", S.next_open(datetime(2026, 10, 23, 20, tzinfo=TZ)).weekday() == 5)
    check("horário inválido (início depois do fim) vira dia fechado", S._clean_days([["18:00", "09:00"]])[0] is None)
    # mensagem fora do expediente
    S.upsert_lead("5521966660001", "Lia", niche_id=1)
    S.exec_tool("5521966660001", "transferir_para_humano", {"motivo": "x"}) if False else None
    S.set_lead("5521966660001", human=1, stage="humano")
    class FakeNow:                      # congela o relógio fora do expediente
        pass
    real_now = S.now_local; S.now_local = lambda: seg_20
    harness.SENT.clear()
    await S.handle_incoming("5521966660001", "Lia", "alguém aí?", "w1")
    sent = [m for m in harness.SENT if m["to"] == "5521966660001"]
    check("lead fala fora do expediente com a conversa na equipe: recebe o aviso com o horário", len(sent) == 1 and "de segunda a sexta" in sent[0]["text"] and "terça" not in sent[0]["text"], sent)
    await S.handle_incoming("5521966660001", "Lia", "e então?", "w2")
    check("o aviso não se repete (12 h)", len([m for m in harness.SENT if m["to"] == "5521966660001"]) == 1)
    check("a IA continua pausada (não responde sozinha)", S.get_lead("5521966660001")["human"] == 1)
    # a IA, ao transferir, é orientada
    S.upsert_lead("5521966660002", "Max", niche_id=1)
    t = S.exec_tool("5521966660002", "transferir_para_humano", {"motivo": "preço"})
    check("transferência fora do expediente: a IA é orientada a informar o horário", "fora do expediente" in t and "20/10" in t, t)
    S.now_local = lambda: seg_10
    S.upsert_lead("5521966660003", "Zé", niche_id=1)
    t = S.exec_tool("5521966660003", "transferir_para_humano", {"motivo": "preço"})
    check("dentro do expediente: sem a observação", "fora do expediente" not in t)
    S.set_lead("5521966660003", human=1, ooh_sent_at=None); harness.SENT.clear()
    await S.handle_incoming("5521966660003", "Zé", "oi", "w3")
    check("dentro do expediente não há aviso", not [m for m in harness.SENT if m["to"] == "5521966660003"])
    # atendente online fora do expediente não recebe aviso em cima
    S.now_local = lambda: seg_20
    a = await S.agents_add(S.AgentIn(name="Ana Lima", login="ana", password="senha-longa-1", max_chats=5))
    la = await S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1")); ta = la["token"]; ida = la["agent"]["id"]
    S.upsert_lead("5521966660004", "Cris", niche_id=1)
    S.exec_tool("5521966660004", "transferir_para_humano", {"motivo": "x"}); harness.SENT.clear()
    await S.handle_incoming("5521966660004", "Cris", "oi, ainda aí?", "w4")
    check("se quem atende está online, não manda o aviso de expediente", S.get_lead("5521966660004")["agent_id"] == ida and not [m for m in harness.SENT if m["to"] == "5521966660004"])
    me = await S.agent_me(x_token=ta)
    check("o atendente vê o status do horário", me["hours"]["enabled"] and not me["hours"]["open_now"] and me["hours"]["next_open"], me["hours"])
    S.now_local = real_now
    # ---- respostas rápidas
    r = await S.quick_add({"title": "Saudação", "body": "Olá {nome}, aqui é {atendente}!"})
    check("cria resposta rápida e o atendente a enxerga", r["ok"] and [x["title"] for x in await S.agent_quick(x_token=ta)] == ["Saudação"])
    check("título/texto vazios são recusados", await code(S.quick_add({"title": "", "body": "x"})) == 400)
    await S.quick_edit(r["id"], {"title": "Saudação", "body": "Oi!"})
    check("editar e apagar", (await S.quick_list())[0]["body"] == "Oi!" and await code(S.quick_edit(999, {"title": "a", "body": "b"})) == 404)
    await S.quick_del(r["id"])
    check("apagada", not await S.quick_list())
    check("rota do atendente exige sessão", await code(S.agent_quick(x_token="lixo")) == 401)
    # ---- notas internas
    ph = "5521966660004"
    n1 = await S.agent_notes_add(ph, S.TextIn(text="Cliente prefere ligação à tarde"), x_token=ta)
    await S.notes_add(ph, S.TextIn(text="Verificar contrato"))
    notes = await S.agent_notes_get(ph, x_token=ta)
    check("nota do atendente e do admin aparecem com o autor", [x["author"] for x in notes] == ["Ana Lima", "Admin"], notes)
    check("notas NUNCA são enviadas ao lead nem entram na conversa", not [m for m in q(S, "SELECT text FROM messages WHERE phone=?", ph) if "ligação" in m["text"]] and not [m for m in harness.SENT if "ligação" in m["text"]])
    check("o agente de IA não vê as notas (não entram no histórico)", "ligação à tarde" not in json.dumps(S.build_system(S.get_lead(ph), S.get_niche(1), "x"), ensure_ascii=False, default=str))
    S.upsert_lead("5521966660009", "Outro", niche_id=1)
    check("atendente não lê nem escreve nota de conversa que não é dele", await code(S.agent_notes_get("5521966660009", x_token=ta)) == 403 and await code(S.agent_notes_add("5521966660009", S.TextIn(text="x"), x_token=ta)) == 403)
    check("nota vazia é recusada", await code(S.agent_notes_add(ph, S.TextIn(text="  "), x_token=ta)) == 400)
    await S.notes_del(n1["id"])
    check("apagar nota", len(await S.notes_get(ph)) == 1)
    # ---- métricas
    S.set_lead(ph, assigned_at=time.time() - 600, handoff_at=time.time() - 660, first_reply_at=None)
    await S.agent_send(ph, S.TextIn2(text="Olá, sou a Ana"), x_token=ta)
    row = q(S, "SELECT first_reply_at,assigned_at FROM leads WHERE phone=?", ph)[0]
    check("a 1ª resposta humana é registrada uma vez", row["first_reply_at"] and 590 < row["first_reply_at"] - row["assigned_at"] < 620, row)
    fr = row["first_reply_at"]
    await S.agent_send(ph, S.TextIn2(text="segunda msg"), x_token=ta)
    check("respostas seguintes não alteram o tempo", q(S, "SELECT first_reply_at FROM leads WHERE phone=?", ph)[0]["first_reply_at"] == fr)
    await S.agent_outcome(ph, S.OutcomeIn(outcome="ganho"), x_token=ta) if hasattr(S, "OutcomeIn") else None
    m = (await S.agents_metrics(30))["agents"][0]
    check("métricas: conversas atendidas, mensagens e tempo de 1ª resposta (mediana)", m["name"] == "Ana Lima" and m["handled"] == 1 and m["messages"] == 2 and 590 < m["first_reply_s"] < 620, m)
    check("métricas: espera na fila", m["queue_wait_s"] is not None and m["queue_wait_s"] >= 0, m)
    check("métricas aparecem para o próprio atendente", (await S.agent_me(x_token=ta))["stats7"]["handled"] == 1)
    S.set_lead(ph, handoff_at=time.time(), first_reply_at=None)
    # nova transferência zera a medição
    S.exec_tool(ph, "transferir_para_humano", {"motivo": "de novo"})
    check("nova transferência reinicia a medição de 1ª resposta", q(S, "SELECT first_reply_at FROM leads WHERE phone=?", ph)[0]["first_reply_at"] is None)
    # LGPD
    S.delete_lead_data(ph) if hasattr(S, "delete_lead_data") else None
    print(f"\n{OK} ok, {FAIL} falha(s)"); sys.exit(1 if FAIL else 0)
asyncio.run(main())
