"""Testa o resumo diário e os conectores Pipedrive/HubSpot (servidores simulados, sem rede)."""
import asyncio, json, os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness

OK = FAIL = 0
def check(nome, cond, extra=""):
    global OK, FAIL
    cond = bool(cond); OK += cond; FAIL += (not cond)
    print(("OK    " if cond else "FALHA ") + nome + ("" if cond else f"  -> {extra}"))
def q(S, sql, *a):
    with S.conn() as c: return [dict(r) for r in c.execute(sql, a)]
def run(S, sql, *a):
    with S.conn() as c: c.execute(sql, a)

async def main():
    S = harness.load_server()
    S.CRM_RETRY = (0, 0, 0)
    await S.pacing_put({"min_delay": 1, "max_delay": 1, "batch_size": 50, "warmup": False, "daily_limit": 500, "reply_delay_min": 0, "reply_delay_max": 0})
    mails = []
    S._send_email = lambda subject, body: mails.append((subject, body))
    os.environ["NOTIFY_EMAIL_TO"] = "gestor@x.com"; os.environ["SMTP_HOST"] = "smtp.example"

    # ================= resumo diário =================
    await S.alerts_put({"whatsapp_to": "21999991111"})
    now = time.time()
    def mk(p, name, stages, replied=True, outcome=""):
        S.upsert_lead(p, name, "", 1)
        S.add_msg(p, "sdr", "oi")
        if replied: S.add_msg(p, "lead", "oi")
        for st in stages: S.set_lead(p, stage=st)
        if outcome: S.set_lead(p, outcome=outcome, handled_at=time.time())
    mk("5511955550001", "Ana", ["qualificando", "qualificado", "encaminhado"]); S.set_lead("5511955550001", alerted_at=now - 1800)
    mk("5511955550002", "Beto", ["qualificando"])
    mk("5511955550003", "Caio", [], replied=False)
    mk("5511955550004", "Duda", ["qualificando", "qualificado", "encaminhado"], outcome="ganho")
    mk("5511955550005", "Edu", ["descartado"])
    S.upsert_lead("5511955550006", "Teste", "", 1, test=1); S.set_lead("5511955550006", stage="encaminhado")
    txt = S.compute_digest()
    check("resumo: leads novos e respostas do dia (teste fora)", "Leads novos: 5" in txt and "Responderam hoje: 4" in txt, txt)
    check("resumo: qualificados, encaminhados e ganhos", "Qualificados: 2 · Encaminhados ao corretor: 2" in txt and "Ganhos: 1" in txt and "Pediram para sair: 1" in txt, txt)
    check("resumo: lista quem aguarda atendimento com o tempo", "Aguardando atendimento (1)" in txt and "Ana" in txt and "há 30 min" in txt, txt)
    check("resumo: mostra o custo do Claude", "Custo do Claude hoje: R$" in txt)
    run(S, "UPDATE leads SET handled_at=? WHERE phone='5511955550001'", time.time())
    check("resumo: sem pendências quando todos foram atendidos", "Nenhum lead aguardando atendimento." in S.compute_digest())
    S.set_setting("autopause", "muitos descartes")
    check("resumo: avisa quando o envio está pausado", "Envios pausados automaticamente: muitos descartes" in S.compute_digest()); run(S, "DELETE FROM settings WHERE k='autopause'")

    check("config do resumo é validada", S.clean_digest_cfg({"hour": 99})["hour"] == 23 and S.clean_digest_cfg({"hour": "abc"})["hour"] == 18)
    check("resumo desligado por padrão: não envia", await S.maybe_digest() is None and not mails)
    await S.digest_put({"enabled": True, "hour": 0, "whatsapp": True, "email": True, "webhook": False})
    check("ligar depois do horário adia o 1º resumo para amanhã", await S.maybe_digest() is None)
    run(S, "DELETE FROM settings WHERE k='last_digest'")
    harness.SENT.clear()
    st = await S.maybe_digest()
    check("resumo enviado por e-mail e WhatsApp do gestor", st == "ok" and len(mails) == 1 and "Resumo do dia" in mails[0][0] and any(m["to"] == "5521999991111" and "Resumo de" in m["text"] for m in harness.SENT), (st, mails, harness.SENT))
    check("resumo: 1 por dia (não repete)", await S.maybe_digest() is None and len(mails) == 1)
    run(S, "DELETE FROM settings WHERE k='last_digest'"); S.set_setting("digest", json.dumps({**S.get_digest_cfg(), "email": False}))
    mails.clear(); harness.SENT.clear(); await S.maybe_digest()
    check("canais desmarcados não recebem", not mails and any(m["to"] == "5521999991111" for m in harness.SENT))
    S.set_setting("digest", json.dumps({**S.get_digest_cfg(), "email": True, "weekdays_only": True}))
    import datetime as dt
    real = S.now_local
    S.now_local = lambda: real().replace(year=2026, month=10, day=24)       # sábado
    run(S, "DELETE FROM settings WHERE k='last_digest'"); mails.clear()
    check("'só dias úteis' não envia no sábado", await S.maybe_digest() is None and not mails)
    S.now_local = real
    r = await S.digest_test()
    check("botão 'enviar agora' envia mesmo fora do horário", r["status"] == "ok")
    g = await S.digest_get()
    check("tela recebe config, canais e prévia", g["config"]["enabled"] and g["channels"]["whatsapp"] and "Leads novos" in g["preview"])
    check("alerta registrado como 'resumo'", q(S, "SELECT 1 FROM alerts WHERE kind='resumo'"))
    await S.digest_put({"enabled": False})

    # ================= Pipedrive =================
    for t in ("leads", "messages", "stage_events", "crm_log", "crm_refs"): run(S, f"DELETE FROM {t}")
    await S.integrations_put({"type": "pipedrive", "pd_domain": "https://minhaempresa.pipedrive.com/", "pd_token": "pdtok"})
    g = await S.integrations_get()
    check("Pipedrive: token nunca volta para a tela", g["has_pd_token"] and "pdtok" not in json.dumps(g) and g["type"] == "pipedrive" and g["active"], g)
    r = await S.integrations_test()
    check("Pipedrive: teste de conexão mostra o usuário", r["ok"] and "Vendedor Teste" in r["detail"], r)
    check("Pipedrive: domínio normalizado", S.pd_base({"pd_domain": "https://minhaempresa.pipedrive.com/"}) == "https://minhaempresa.pipedrive.com/api/v1")
    await S.integrations_put({"pd_token": "errado"})
    r = await S.integrations_test()
    check("Pipedrive: token errado informa HTTP 401", not r["ok"] and "401" in r["detail"], r)
    await S.integrations_put({"pd_token": "pdtok"})
    S.upsert_lead("5511944440001", "Carla Dias", "Loja X", 1)
    S.set_lead("5511944440001", bant=json.dumps({"temperatura": "quente", "resumo_encaminhamento": "Casal, Campinas", "cidade": "Campinas"}), stage="encaminhado"); await asyncio.sleep(0.5)
    P = harness.PD
    check("Pipedrive: criou pessoa com telefone +55...", len(P["persons"]) == 1 and P["persons"][0]["phone"][0]["value"] == "+5511944440001" and P["persons"][0]["name"] == "Carla Dias", P["persons"])
    check("Pipedrive: criou negócio ligado à pessoa", len(P["deals"]) == 1 and list(P["deals"].values())[0]["person_id"] == P["persons"][0]["id"] and "Carla Dias" in list(P["deals"].values())[0]["title"])
    check("Pipedrive: nota com resumo, temperatura e dados", len(P["notes"]) == 1 and "Casal, Campinas" in P["notes"][0]["content"] and "quente" in P["notes"][0]["content"] and "cidade: Campinas" in P["notes"][0]["content"], P["notes"])
    S.set_lead("5511944440001", stage="reuniao_agendada", meeting="2026-10-21 15:30"); await asyncio.sleep(0.5)
    check("Pipedrive: atividade de reunião em UTC (15:30 BRT = 18:30)", len(P["acts"]) == 1 and P["acts"][0]["due_time"] == "18:30" and P["acts"][0]["due_date"] == "2026-10-21" and P["acts"][0]["type"] == "meeting", P["acts"])
    check("Pipedrive: mesma pessoa e negócio (sem duplicar)", len(P["persons"]) == 1 and len(P["deals"]) == 1)
    await S.set_outcome("5511944440001", S.OutcomeIn(outcome="ganho")); await asyncio.sleep(0.5)
    check("Pipedrive: 'ganho' marca o negócio como won", list(P["deals"].values())[0]["status"] == "won")
    S.upsert_lead("5511944440002", "Davi", "", 1); S.set_lead("5511944440002", stage="encaminhado"); await asyncio.sleep(0.4)
    await S.set_outcome("5511944440002", S.OutcomeIn(outcome="perdido", reason="achou caro")); await asyncio.sleep(0.4)
    d2 = [d for d in P["deals"].values() if "Davi" in d["title"]][0]
    check("Pipedrive: 'perdido' vai como lost com o motivo", d2["status"] == "lost" and d2["lost_reason"] == "achou caro", d2)
    P["persons"].append({"id": 777, "name": "Já existia", "phone": [{"value": "+5511944440003", "primary": True}]})
    S.upsert_lead("5511944440003", "Eva", "", 1); S.set_lead("5511944440003", stage="encaminhado"); await asyncio.sleep(0.4)
    check("Pipedrive: reaproveita pessoa que já existe (busca por telefone)", len(P["persons"]) == 3 and list(P["deals"].values())[-1]["person_id"] == 777, P["deals"])
    S.upsert_lead("5511944440004", "Fabi", "", 1); S.set_lead("5511944440004", stage="descartado"); await asyncio.sleep(0.4)
    check("Pipedrive: 'descartado' não cria negócio", not [d for d in P["deals"].values() if "Fabi" in d["title"]])
    P["fail"] = 1
    S.upsert_lead("5511944440005", "Gil", "", 1); S.set_lead("5511944440005", stage="encaminhado"); await asyncio.sleep(0.5)
    check("Pipedrive: falha temporária (HTTP 500) é repetida e conclui", [d for d in P["deals"].values() if "Gil" in d["title"]] and q(S, "SELECT status FROM crm_log WHERE phone='5511944440005'")[0]["status"] == "ok")
    P["fail"] = 99
    S.upsert_lead("5511944440006", "Hugo", "", 1); S.set_lead("5511944440006", stage="encaminhado"); await asyncio.sleep(0.5)
    lg = q(S, "SELECT status,detail FROM crm_log WHERE phone='5511944440006'")
    check("Pipedrive: falha persistente fica no log com o motivo", lg and lg[0]["status"] == "erro" and "HTTP 500" in lg[0]["detail"], lg)
    P["fail"] = 0
    S.upsert_lead("5511944440009", "Teste", "", 1, test=1); n0 = len(P["calls"]); S.set_lead("5511944440009", stage="encaminhado"); await asyncio.sleep(0.3)
    check("lead de teste nunca vai ao Pipedrive", len(P["calls"]) == n0)

    # ================= HubSpot =================
    H = harness.HS
    await S.integrations_put({"type": "hubspot", "hs_token": "hstok"})
    g = await S.integrations_get()
    check("HubSpot: token não volta para a tela", g["has_hs_token"] and "hstok" not in json.dumps(g) and g["type"] == "hubspot")
    r = await S.integrations_test(); check("HubSpot: teste de conexão", r["ok"] and r["detail"] == "conectado", r)
    await S.integrations_put({"hs_token": "ruim"}); r = await S.integrations_test()
    check("HubSpot: token errado informa 401", not r["ok"] and "401" in r["detail"], r)
    await S.integrations_put({"hs_token": "hstok"})
    S.upsert_lead("5511933330001", "Ivo Santos Lima", "Oficina Y", 1)
    S.set_lead("5511933330001", bant=json.dumps({"temperatura": "morno", "resumo_encaminhamento": "Frota de 3 carros"}), stage="encaminhado"); await asyncio.sleep(0.6)
    check("HubSpot: criou contato (nome, sobrenome, telefone, empresa)", len(H["contacts"]) == 1 and H["contacts"][0]["properties"] == {"firstname": "Ivo", "lastname": "Santos Lima", "phone": "+5511933330001", "company": "Oficina Y"}, H["contacts"])
    deal = list(H["deals"].values())[0]
    check("HubSpot: negócio no pipeline/estágio padrão e associado ao contato", deal["properties"]["pipeline"] == "default" and deal["properties"]["dealstage"] == "appointmentscheduled" and H["assoc"] and H["assoc"][0].endswith("/contacts/900"), (deal, H["assoc"]))
    nt = H["notes"][0]
    check("HubSpot: nota associada a contato (202) e negócio (214)", {a["types"][0]["associationTypeId"] for a in nt["associations"]} == {202, 214} and "Frota de 3 carros" in nt["properties"]["hs_note_body"], nt)
    await S.set_outcome("5511933330001", S.OutcomeIn(outcome="ganho")); await asyncio.sleep(0.5)
    check("HubSpot: 'ganho' move para closedwon", list(H["deals"].values())[0]["properties"]["dealstage"] == "closedwon")
    S.upsert_lead("5511933330001", "Ivo", "", 1)
    run(S, "DELETE FROM crm_refs WHERE phone='5511933330001'"); n = len(H["contacts"])
    S.set_lead("5511933330001", stage="humano"); await asyncio.sleep(0.5)
    check("HubSpot: reaproveita contato existente (sem duplicar)", len(H["contacts"]) == n)
    H["fail"] = 2
    S.upsert_lead("5511933330002", "Jô", "", 1); S.set_lead("5511933330002", stage="encaminhado"); await asyncio.sleep(0.6)
    check("HubSpot: limite de taxa (429) é repetido e conclui", q(S, "SELECT status FROM crm_log WHERE phone='5511933330002'")[0]["status"] == "ok")
    await S.integrations_put({"hs_stage_won": "meu_ganho", "hs_pipeline": "vendas"})
    check("HubSpot: pipeline e estágios configuráveis", S.get_integrations()["hs_pipeline"] == "vendas" and S.get_integrations()["hs_stage_won"] == "meu_ganho")
    # filtro de eventos vale para os conectores
    await S.integrations_put({"events": ["ganho"]})
    n0 = len(H["calls"]); S.upsert_lead("5511933330003", "Kiko", "", 1); S.set_lead("5511933330003", stage="encaminhado"); await asyncio.sleep(0.4)
    check("eventos desmarcados não são sincronizados", len(H["calls"]) == n0)
    try: await S.integrations_put({"type": "salesforce"}); check("destino desconhecido é recusado", False)
    except harness.HTTPException as e: check("destino desconhecido é recusado", e.status_code == 400)
    await S.integrations_put({"type": "webhook", "url": ""})
    check("voltar para webhook sem URL desativa a integração", not (await S.integrations_get())["active"])
    os.environ["NOTIFY_EMAIL_TO"] = ""

    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
