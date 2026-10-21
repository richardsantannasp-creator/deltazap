"""Testa avisos ao corretor, SLA, retomada automática, resultado do lead e funil (sem rede; WhatsApp/Claude/e-mail simulados)."""
import asyncio, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import harness

OK = FAIL = 0
def check(nome, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1
    else: FAIL += 1
    print(("OK    " if cond else "FALHA ") + nome + ("" if cond else f"  -> {extra}"))

H = 3600
def q(S, sql, *a):
    with S.conn() as c: return [dict(r) for r in c.execute(sql, a)]
def run(S, sql, *a):
    with S.conn() as c: c.execute(sql, a)
def mk(S, phone, name="Ana", stage="contatado", niche=1, hours_ago=0, last="sdr"):
    S.upsert_lead(phone, name, "", niche)
    S.set_lead(phone, stage=stage)
    t = time.time() - hours_ago * H
    run(S, "DELETE FROM messages WHERE phone=?", phone)
    S.add_msg(phone, "sdr", "Olá! posso te ajudar?")
    if last == "lead": S.add_msg(phone, "lead", "quero sim")
    run(S, "UPDATE messages SET ts=? WHERE phone=?", t, phone)
async def tick(S):
    S.NEXT_AT = 0; S.LINE_NEXT.clear(); S.LINE_STATE_TS = 0; await S.outbox_tick()

async def main():
    S = harness.load_server()
    mails = []
    S._send_email = lambda subject, body: mails.append((subject, body))
    await S.pacing_put({"min_delay": 1, "max_delay": 1, "batch_size": 50, "warmup": False, "daily_limit": 500, "reply_delay_min": 0, "reply_delay_max": 0})
    S.now_local = S.now_local  # horário real; o SLA é testado ajustando start/end

    # ---- configuração de avisos
    cfg = S.clean_alerts_cfg({"whatsapp_to": "(21) 99999-1111, 5511988887777;abc", "sla_min": 0, "repeat_min": 1, "start_hour": 22, "end_hour": 3, "max_reminders": 99})
    check("números do corretor normalizados (DDI 55 e lixo descartado)", cfg["whatsapp_to"] == "5521999991111,5511988887777", cfg["whatsapp_to"])
    check("limites do SLA ajustados", cfg["sla_min"] == 1 and cfg["repeat_min"] == 5 and cfg["max_reminders"] == 10 and cfg["end_hour"] > cfg["start_hour"], cfg)
    await S.alerts_put({"whatsapp_to": "21999991111", "sla_min": 15, "repeat_min": 30, "max_reminders": 2, "start_hour": 0, "end_hour": 24})

    # ---- aviso de lead encaminhado (WhatsApp + e-mail + webhook)
    os.environ.update(NOTIFY_EMAIL_TO="a@x.com,b@x.com", SMTP_HOST="smtp.example", NOTIFY_WEBHOOK_URL="https://hooks.example/ok", PUBLIC_URL="https://painel.example")
    await S.handle_incoming("5511999990001", "Carla", "oi quero plano de saude", None, True)
    await S.handle_incoming("5511999990001", "Carla", "somos um casal e moramos em Campinas", None, True)
    lead = S.get_lead("5511999990001")
    check("lead foi encaminhado e marcado como aguardando", lead["stage"] == "encaminhado" and lead["alerted_at"] and not lead["handled_at"], lead)
    corretor = [m for m in harness.SENT if m["to"] == "5521999991111"]
    check("corretor recebeu o aviso no WhatsApp com nome, telefone e link", len(corretor) == 1 and "Carla" in corretor[0]["text"] and "5511999990001" in corretor[0]["text"] and "painel.example" in corretor[0]["text"], corretor)
    check("aviso por e-mail enviado", len(mails) == 1 and "Carla" in mails[0][0], mails)
    check("webhook recebeu text e content", len(harness.HOOKS) == 1 and harness.HOOKS[0]["text"] == harness.HOOKS[0]["content"] and "Carla" in harness.HOOKS[0]["text"], harness.HOOKS)
    al = q(S, "SELECT kind,status,channels FROM alerts")
    check("alerta registrado com status ok nos 3 canais", len(al) == 1 and al[0]["status"] == "ok" and al[0]["channels"].count(":ok") == 3, al)

    # ---- lead de teste e tipo desligado não alertam
    n0 = len(q(S, "SELECT 1 FROM alerts"))
    S.upsert_lead("5511999990002", "Teste", "", 1, test=1)
    await S.notify("encaminhado", "5511999990002", "x")
    await S.alerts_put({"on_reuniao": False})
    mk(S, "5511999990003", "Beto", "reuniao_agendada"); await S.notify("reuniao", "5511999990003", "x")
    check("lead de teste e tipo desligado não geram alerta", len(q(S, "SELECT 1 FROM alerts")) == n0)
    await S.alerts_put({"on_reuniao": True})

    # ---- resposta de lead não atendido (1 por 10 min)
    harness.SENT.clear()
    await S.handle_incoming("5511999990001", "Carla", "alguém aí?", None, True)
    await S.handle_incoming("5511999990001", "Carla", "ok??", None, True)
    await asyncio.sleep(0.3)
    resp = q(S, "SELECT 1 FROM alerts WHERE kind='resposta'")
    check("resposta de lead aguardando gera 1 alerta (sem repetir em 10 min)", len(resp) == 1, resp)

    # ---- SLA
    run(S, "UPDATE leads SET alerted_at=? WHERE phone='5511999990001'", time.time() - 5 * 60)
    check("SLA: antes do prazo não lembra", await S.sla_scan() == 0)
    run(S, "UPDATE leads SET alerted_at=? WHERE phone='5511999990001'", time.time() - 20 * 60)
    check("SLA: depois do prazo lembra 1x", await S.sla_scan() == 1)
    check("SLA: não repete antes do intervalo", await S.sla_scan() == 0)
    run(S, "UPDATE leads SET last_reminder_at=? WHERE phone='5511999990001'", time.time() - 31 * 60)
    check("SLA: repete após o intervalo", await S.sla_scan() == 1)
    run(S, "UPDATE leads SET last_reminder_at=? WHERE phone='5511999990001'", time.time() - 31 * 60)
    check("SLA: para no máximo de lembretes (2)", await S.sla_scan() == 0)
    run(S, "UPDATE leads SET reminders=0,last_reminder_at=NULL WHERE phone='5511999990001'")
    await S.mark_handled("5511999990001")
    check("SLA: lead atendido não recebe lembrete", await S.sla_scan() == 0)
    run(S, "UPDATE leads SET handled_at=NULL,reminders=0 WHERE phone='5511999990001'")
    h = S.now_local().hour
    await S.alerts_put({"start_hour": (h + 2) % 24 if h + 2 < 23 else 0, "end_hour": (h + 3) if h + 3 <= 24 else 24})
    if h + 2 < 23: check("SLA: fora do horário comercial não lembra", await S.sla_scan() == 0)
    await S.alerts_put({"start_hour": 0, "end_hour": 24})
    r = await S.alerts_test()
    check("botão de teste envia aviso", r["status"] == "ok", r)

    # webhook com falha não derruba
    os.environ["NOTIFY_WEBHOOK_URL"] = "https://hooks.example/falha"
    st = await S.notify("teste", None, "x")
    check("falha de um canal não impede os outros", st == "ok", st)
    os.environ.pop("NOTIFY_WEBHOOK_URL"); os.environ.pop("NOTIFY_EMAIL_TO")

    # ---- resultado do lead
    for bad in ("xyz",):
        try: await S.set_outcome("5511999990001", S.OutcomeIn(outcome=bad)); check("resultado inválido é recusado", False)
        except harness.HTTPException as e: check("resultado inválido é recusado", e.status_code == 400)
    await S.set_outcome("5511999990001", S.OutcomeIn(outcome="ganho", reason="fechou"))
    l = S.get_lead("5511999990001")
    check("resultado 'ganho' salvo e lead marcado como atendido", l["outcome"] == "ganho" and l["handled_at"], l)

    # ---- retomada: cadência
    await S.cadence_put({"enabled": True, "steps": [{"delay_h": 24, "mode": "claude"}, {"delay_h": 48, "mode": "fixo", "text": "Oi {nome}, seguimos por aqui!"}, {"delay_h": 96, "mode": "claude"}]})
    run(S, "DELETE FROM outbox")
    mk(S, "5511999991001", "Davi", hours_ago=30)                 # vencido
    mk(S, "5511999991002", "Eva", hours_ago=5)                    # ainda não venceu
    mk(S, "5511999991003", "Fabio", hours_ago=30, last="lead")    # lead falou por último
    mk(S, "5511999991004", "Gil", "encaminhado", hours_ago=30)    # já encaminhado
    mk(S, "5511999991005", "Hana", hours_ago=30); S.set_lead("5511999991005", human=1)
    mk(S, "5511999991006", "Ivo", hours_ago=30); S.set_lead("5511999991006", outcome="perdido")
    mk(S, "5511999991007", "Joao", hours_ago=30, niche=2)         # nicho com retomada desligada
    run(S, "UPDATE niches SET followup=0 WHERE id=2")
    n = await S.followup_scan()
    check("só o lead parado e vencido entra na fila", n == 1 and q(S, "SELECT phone FROM outbox WHERE kind='followup'")[0]["phone"] == "5511999991001", q(S, "SELECT * FROM outbox"))
    check("scan repetido não duplica", await S.followup_scan() == 0)
    prev = await S.followups_preview()
    check("prévia lista quem está esperando", any(p["phone"] == "5511999991002" and p["due_min"] > 0 for p in prev), prev)

    harness.SENT.clear()
    await tick(S)
    sent = [m for m in harness.SENT if m["to"] == "5511999991001"]
    l = S.get_lead("5511999991001")
    check("retomada 1 enviada (Claude), com digitação e opção SAIR", len(sent) == 1 and sent[0]["typing_ms"] > 0 and "SAIR" in sent[0]["text"], sent)
    check("contador de retomadas = 1 e mensagem marcada", l["followups_sent"] == 1 and q(S, "SELECT 1 FROM messages WHERE phone='5511999991001' AND kind='followup'"))

    # etapa 2 (texto fixo)
    run(S, "UPDATE messages SET ts=ts-? WHERE phone='5511999991001'", 50 * H)
    check("etapa 2 entra na fila após o prazo", await S.followup_scan() == 1)
    harness.SENT.clear(); await tick(S)
    check("etapa 2 usa o texto fixo com {nome}", any("Oi Davi, seguimos por aqui!" in m["text"] for m in harness.SENT), harness.SENT)

    # etapa 3 = final -> sem_resposta
    run(S, "UPDATE messages SET ts=ts-? WHERE phone='5511999991001'", 100 * H)
    await S.followup_scan(); harness.SENT.clear(); await tick(S)
    l = S.get_lead("5511999991001")
    check("última retomada leva o lead a 'sem_resposta'", l["stage"] == "sem_resposta" and l["followups_sent"] == 3, l)
    check("não há mais retomadas depois da cadência", await S.followup_scan() == 0)

    # lead responde -> reinicia
    await S.handle_incoming("5511999991001", "Davi", "voltei, quero saber mais", None, True)
    l = S.get_lead("5511999991001")
    check("resposta do lead zera a cadência e reabre o atendimento", l["followups_sent"] == 0 and l["stage"] in ("qualificando", "contatado"), l)

    # cancela se o lead respondeu entre a fila e o envio
    mk(S, "5511999991010", "Kai", hours_ago=30); await S.followup_scan()
    S.add_msg("5511999991010", "lead", "oi!")
    harness.SENT.clear(); await tick(S)
    check("retomada é cancelada se o lead respondeu antes do envio", not [m for m in harness.SENT if m["to"] == "5511999991010"] and
          q(S, "SELECT status FROM outbox WHERE phone='5511999991010'")[0]["status"] == "skipped")
    run(S, "UPDATE messages SET ts=ts-? WHERE phone='5511999991010'", 0)

    # SAIR depois da retomada
    mk(S, "5511999991011", "Lia", hours_ago=30); await S.followup_scan(); await tick(S)
    await S.handle_incoming("5511999991011", "Lia", "SAIR", None, True)
    check("SAIR após retomada descarta o lead", S.get_lead("5511999991011")["stage"] == "descartado")

    # número sem WhatsApp não fica em loop
    mk(S, "5511999991404", "Zed", hours_ago=30); await S.followup_scan(); await tick(S)
    run(S, "UPDATE messages SET ts=ts-1 WHERE phone='5511999991404'")
    check("etapa pulada/falha não volta para a fila", await S.followup_scan() == 0)

    # API oficial fora da janela exige template
    S.PROVIDER = "official"
    mk(S, "5511999991020", "Mia", hours_ago=30); run(S, "INSERT INTO messages(phone,role,text,ts) VALUES('5511999991020','lead','oi',?)", time.time() - 40 * H)
    run(S, "UPDATE messages SET ts=ts-? WHERE phone='5511999991020' AND role='sdr'", 0)
    # a última msg precisa ser do sdr: reinsere
    S.add_msg("5511999991020", "sdr", "Olá de novo"); run(S, "UPDATE messages SET ts=? WHERE phone='5511999991020' AND text='Olá de novo'", time.time() - 30 * H)
    await S.followup_scan(); await tick(S)
    st = q(S, "SELECT status,error FROM outbox WHERE phone='5511999991020'")
    check("API oficial fora da janela sem template: etapa é pulada com motivo", st and st[0]["status"] == "skipped" and "template" in st[0]["error"], st)
    S.PROVIDER = "qr"

    # ---- funil (banco limpo para contas exatas)
    S2 = S
    for t in ("leads", "messages", "stage_events", "outbox", "alerts"): run(S2, f"DELETE FROM {t}")
    now = time.time()
    def lead(p, stages, replied, outcome="", origin="ativo", niche=1):
        S.upsert_lead(p, "L" + p[-2:], "", niche, origin=origin)
        run(S, "UPDATE leads SET created=? WHERE phone=?", now - 3 * H, p)
        S.add_msg(p, "sdr", "oi"); run(S, "UPDATE messages SET ts=? WHERE phone=?", now - 3 * H, p)
        if replied: S.add_msg(p, "lead", "oi"); run(S, "UPDATE messages SET ts=? WHERE phone=? AND role='lead'", now - 3 * H + 600, p)
        for i, s in enumerate(stages):
            S.set_lead(p, stage=s); run(S, "UPDATE stage_events SET ts=? WHERE phone=? AND stage=?", now - 2 * H + i * 60, p, s)
        if outcome: S.set_lead(p, outcome=outcome)
    lead("5511900000001", [], False)
    lead("5511900000002", [], False)
    lead("5511900000003", ["qualificando"], True)
    lead("5511900000004", ["qualificando", "qualificado"], True)
    lead("5511900000005", ["qualificando", "qualificado", "encaminhado"], True)
    lead("5511900000006", ["qualificando", "qualificado", "encaminhado"], True, "ganho")
    lead("5511900000007", ["qualificando", "descartado"], True)
    lead("5511900000008", ["qualificando", "qualificado", "encaminhado", "reuniao_agendada"], True, "perdido")
    S.upsert_lead("5511900000009", "Teste", "", 1, test=1)
    f = S.compute_funnel(30)
    counts = [s["count"] for s in f["steps"]]
    check("funil: contagens por etapa [8,6,4,3,1]", counts == [8, 6, 4, 3, 1], counts)
    check("funil: lead de teste fora da conta", f["total"] == 8)
    check("funil: percentuais", f["steps"][1]["pct_total"] == 75.0 and f["steps"][2]["pct_prev"] == 66.7, f["steps"])
    check("funil: laterais (reunião, descartado, perdido)", f["side"]["reunioes"] == 1 and f["side"]["descartados"] == 1 and f["side"]["perdidos"] == 1, f["side"])
    check("funil: tempo mediano até a 1ª resposta = 10 min", f["times"]["first_reply_min"] == 10.0, f["times"])
    check("funil: por nicho e série diária", f["by_niche"] and f["by_niche"][0]["leads"] == 8 and len(f["daily"]) == 14 and sum(x["leads"] for x in f["daily"][-2:]) == 8, (f["by_niche"], f["daily"][-2:]))
    check("funil: período curto/filtro", S.compute_funnel(0)["days"] == 1 and S.compute_funnel(9999)["days"] == 365)
    old = q(S, "SELECT 1")  # smoke do endpoint
    check("endpoint /api/funnel devolve o mesmo cálculo", (await S.funnel(30))["total"] == 8)

    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
