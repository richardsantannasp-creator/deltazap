"""Testa vários números (linhas) no modo QR: cadastro, ritmo por número, distribuição, respostas e retomadas pelo número certo."""
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
async def tick(S):
    S.NEXT_AT = 0; S.LINE_NEXT.clear(); S.LINE_STATE_TS = 0; await S.outbox_tick()
def sent_by(line, skip=()):
    return [m for m in harness.SENT if m.get("line") == line and m["to"] not in skip]
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0

async def main():
    S = harness.load_server()
    await S.pacing_put({"min_delay": 1, "max_delay": 1, "batch_size": 50, "warmup": False, "daily_limit": 500, "reply_delay_min": 0, "reply_delay_max": 0,
                        "start_hour": 0, "end_hour": 24, "weekdays_only": False})
    S.LINES_MAX = 3

    # ---------- cadastro ----------
    r = await S.lines_get()
    check("começa só com o número principal", [l["id"] for l in r["lines"]] == ["main"] and r["max"] == 3, r)
    check("nome vazio é recusado", await err(S.lines_add({"label": "  "})) == 400)
    a = await S.lines_add({"label": "Comercial 2"})
    check("novo número recebe um id curto e entra no gateway", a["id"] == "comercial-2" and "comercial-2" in harness.GWL, a)
    b = await S.lines_add({"label": "Comercial 2"})
    check("nomes repetidos ganham ids diferentes", b["id"] == "comercial-2-2", b)
    check("limite de números é respeitado", await err(S.lines_add({"label": "Outro"})) == 400)
    await S.lines_delete("comercial-2-2")
    check("remover número tira do gateway e do cadastro", "comercial-2-2" not in harness.GWL and not S.known_line("comercial-2-2"))
    check("o número principal não pode ser removido", await err(S.lines_delete("main")) == 400)
    check("remover número inexistente dá 404", await err(S.lines_delete("zzz")) == 404)
    c = await S.connection(line="comercial-2")
    check("estado e QR de cada número são independentes", c["state"] == "qr" and c["qr"] and (await S.connection())["state"] == "open", c)
    check("número desconhecido dá 404 na conexão", await err(S.connection(line="zzz")) == 404)
    p = await S.connection_pair(S.PairIn(phone="21999990002"), line="comercial-2")
    check("código de pareamento por número", p.get("code") == "ABCD-EFGH", p)

    # ---------- distribuição ----------
    rows = "\n".join(f"55119888800{i:02d};Lead {i}" for i in range(1, 7))
    harness.SENT.clear()
    assert (await S.dispatch(S.DispatchIn(niche_id=1, lines=rows, consent=True, origem="lista de teste"), S.BackgroundTasks()))["queued"] == 6
    for _ in range(3): await tick(S)
    check("com o 2º número desconectado, tudo sai pelo principal", len(sent_by("main")) == 3 and not sent_by("comercial-2"), harness.SENT)
    harness.GWL["comercial-2"]["state"] = "open"
    for _ in range(3): await tick(S)
    check("conectado o 2º número, a fila é dividida entre os dois", len(sent_by("main")) >= 3 and len(sent_by("comercial-2")) >= 2 and len(harness.SENT) == 6,
          [(m["to"][-2:], m["line"]) for m in harness.SENT])
    sent_leads = {m["to"]: m["line"] for m in harness.SENT}
    check("cada lead fica ligado ao número que o contatou", all(S.get_lead(ph)["line"] == ln for ph, ln in sent_leads.items()))
    check("a fila registra o número usado", {r["phone"]: r["line"] for r in q(S, "SELECT phone,line FROM outbox WHERE status='sent'")} == sent_leads)

    # ---------- escolher o número no disparo ----------
    harness.SENT.clear()
    rows2 = "5511977770001;Ana\n5511977770002;Bia"
    check("disparo com número inexistente é recusado", await err(S.dispatch(S.DispatchIn(niche_id=1, lines=rows2, consent=True, origem="lista de teste", line="zzz"), S.BackgroundTasks())) == 400)
    await S.dispatch(S.DispatchIn(niche_id=1, lines=rows2, consent=True, origem="lista de teste", line="comercial-2"), S.BackgroundTasks())
    for _ in range(3): await tick(S)
    check("disparo fixado num número sai só por ele", len(harness.SENT) == 2 and all(m["line"] == "comercial-2" for m in harness.SENT), harness.SENT)
    harness.SENT.clear()
    await S.dispatch(S.DispatchIn(niche_id=1, lines="5511977770003;Caio\n5511977770004;Duda", consent=True, origem="lista de teste", line="comercial-2"), S.BackgroundTasks())
    harness.GWL["comercial-2"]["state"] = "qr"
    for _ in range(2): await tick(S)
    left = q(S, "SELECT status FROM outbox WHERE phone IN ('5511977770003','5511977770004')")
    check("se o número escolhido cai, os contatos esperam nele (não passam para outro)", not harness.SENT and all(r["status"] == "queued" for r in left), (harness.SENT, left))
    harness.GWL["comercial-2"]["state"] = "open"
    for _ in range(2): await tick(S)
    check("quando volta, o número retoma a fila", len(sent_by("comercial-2")) == 2, harness.SENT)

    # ---------- respostas e retomadas ----------
    harness.SENT.clear()
    await S.handle_incoming("5511966660001", "Eva", "oi quero plano de saude", None, True, line="comercial-2")
    eva = [m for m in harness.SENT if m["to"] == "5511966660001"]
    check("quem chama o 2º número é respondido por ele", eva and all(m["line"] == "comercial-2" for m in eva) and S.get_lead("5511966660001")["line"] == "comercial-2", eva)
    await S.handle_incoming("5511966660002", "Fábio", "oi quero plano de saude", None, True)
    check("sem número informado, vale o principal", S.lead_line("5511966660002") == "main" and all(m["line"] == "main" for m in harness.SENT if m["to"] == "5511966660002"))
    await S.handle_incoming("5511966660001", "Eva", "e o preço?", None, True, line="main")
    check("se o lead passa a falar com outro número, a conversa segue por ele", S.get_lead("5511966660001")["line"] == "main")
    await S.handle_incoming("5511966660001", "Eva", "voltei aqui", None, True, line="comercial-2")

    await S.cadence_put({"enabled": True, "steps": [{"delay_h": 1, "mode": "fixo", "text": "Oi {nome}, seguimos por aqui!"}]})
    S.upsert_lead("5511955550009", "Gil", "", 1); S.set_lead("5511955550009", stage="contatado", line="comercial-2")
    S.add_msg("5511955550009", "sdr", "Olá!")
    run(S, "UPDATE messages SET ts=? WHERE phone='5511955550009'", time.time() - 3 * 3600)
    harness.SENT.clear()
    check("retomada entra na fila ligada ao número do lead", await S.followup_scan() >= 1 and q(S, "SELECT line FROM outbox WHERE phone='5511955550009' AND kind='followup'")[0]["line"] == "comercial-2")
    for _ in range(3): await tick(S)
    gil = [m for m in harness.SENT if m["to"] == "5511955550009"]
    check("a retomada sai pelo mesmo número", len(gil) == 1 and gil[0]["line"] == "comercial-2", harness.SENT)

    # ---------- avisos internos ----------
    await S.alerts_put({"whatsapp_to": "21999991111"})
    harness.SENT.clear(); harness.GW["state"] = "closed"; S.LINE_STATE_TS = 0; await S.refresh_lines_state(force=True)
    check("avisos internos usam outro número se o principal cair", S.internal_line() == "comercial-2")
    await S.notify("teste", None, "oi")
    av = [m for m in harness.SENT if m["to"] == "5521999991111"]
    check("o aviso ao corretor sai pelo número conectado", len(av) == 1 and av[0]["line"] == "comercial-2", harness.SENT)
    harness.GW["state"] = "open"; await S.refresh_lines_state(force=True)

    # ---------- limite diário e aquecimento por número ----------
    run(S, "DELETE FROM outbox"); harness.SENT.clear()
    await S.pacing_put({"daily_limit": 2, "warmup": False})
    await S.dispatch(S.DispatchIn(niche_id=1, lines="\n".join(f"551194440{i:03d};X{i}" for i in range(10)), consent=True, origem="lista de teste"), S.BackgroundTasks())
    for _ in range(12): await tick(S)
    check("o limite diário vale para cada número", len(sent_by("main")) == 2 and len(sent_by("comercial-2")) == 2 and len(harness.SENT) == 4, [(m["line"]) for m in harness.SENT])
    check("o resto continua na fila para amanhã", q(S, "SELECT COUNT(*) n FROM outbox WHERE status='queued'")[0]["n"] == 6)
    m = await S.metrics_api()
    check("métricas somam os limites e detalham por número", m["allowed_today"] == 4 and m["sent_today"] >= 4 and {x["id"] for x in m["by_line"]} == {"main", "comercial-2"}, m["by_line"])
    await S.pacing_put({"daily_limit": 100, "warmup": True})
    from datetime import date, timedelta
    old = (date.today() - timedelta(days=10)).isoformat()
    run(S, "UPDATE lines SET first_send_day=? WHERE id='main'", old); run(S, "UPDATE lines SET first_send_day='' WHERE id='comercial-2'")
    cfg = S.get_pacing()
    check("o aquecimento é por número (o novo começa pequeno, o antigo já cresceu)",
          S.allowed_today(cfg, "comercial-2") == S.WARMUP_START and S.allowed_today(cfg, "main") > S.WARMUP_START, (S.allowed_today(cfg, "main"), S.allowed_today(cfg, "comercial-2")))
    run(S, "DELETE FROM outbox"); harness.SENT.clear()
    await S.pacing_put({"daily_limit": 500, "warmup": False})
    run(S, "UPDATE lines SET first_send_day='' WHERE id='comercial-2'")
    await S.dispatch(S.DispatchIn(niche_id=1, lines="5511933330001;Z", consent=True, origem="lista de teste", line="comercial-2"), S.BackgroundTasks())
    await tick(S)
    check("o primeiro envio de um número marca o início do aquecimento dele", q(S, "SELECT first_send_day f FROM lines WHERE id='comercial-2'")[0]["f"] == date.today().isoformat())

    # ---------- falhas em um número não param os outros ----------
    run(S, "DELETE FROM outbox"); harness.SENT.clear(); run(S, "UPDATE lines SET active=0 WHERE id='main'")
    S.set_setting("autopause", "")
    await S.dispatch(S.DispatchIn(niche_id=1, lines="\n".join(f"551192220{i:03d};F{i}" for i in range(5)), consent=True, origem="lista de teste", line="comercial-2"), S.BackgroundTasks())
    await S.lines_put("main", {"active": True})
    for _ in range(3):
        S.NEXT_AT = 0; S.LINE_NEXT.clear(); S.LINE_STATE_TS = time.time()      # estado em cache continua "conectado"...
        harness.GWL["comercial-2"]["state"] = "closed"                         # ...mas o envio de fato falha
        await S.outbox_tick()
    check("3 falhas de um número com outro ativo põem só ele em espera (sem pausa geral)", not S.get_setting("autopause") and S.LINE_NEXT.get("comercial-2", 0) > time.time() + 1500, (S.get_setting("autopause"), S.LINE_NEXT))
    harness.GWL["comercial-2"]["state"] = "open"

    # ---------- remover número com fila e leads ----------
    run(S, "DELETE FROM outbox"); S.LINE_NEXT.clear()
    await S.dispatch(S.DispatchIn(niche_id=1, lines="5511922220001;R", consent=True, origem="lista de teste", line="comercial-2"), S.BackgroundTasks())
    await S.lines_delete("comercial-2")
    check("remover um número libera a fila dele e os leads voltam ao principal",
          q(S, "SELECT line FROM outbox WHERE phone='5511922220001'")[0]["line"] == "" and S.lead_line("5511966660001") == "main" and S.active_lines() == ["main"])
    harness.SENT.clear(); await tick(S)
    check("o contato solto sai pelo número que sobrou", len(sent_by("main")) == 1, harness.SENT)

    # ---------- campos [..] sem preencher e SAIR obrigatório ----------
    run(S, "DELETE FROM outbox"); harness.SENT.clear()
    blank = q(S, "SELECT id FROM niches WHERE name='Modelo em branco'")[0]["id"]
    code = await err(S.dispatch(S.DispatchIn(niche_id=blank, lines="5511900000001;Teste", consent=True, origem="lista de teste"), S.BackgroundTasks()))
    check("disparo com nicho de campos [NOME]/[EMPRESA] sem preencher é recusado", code == 400 and not q(S, "SELECT 1 FROM outbox"))
    run(S, "INSERT INTO outbox(phone,niche_id,name,created) VALUES('5511900000002',?,'X',?)", blank, time.time())
    await tick(S)
    check("item antigo da fila com campos sem preencher não é enviado", not harness.SENT and q(S, "SELECT status,error FROM outbox WHERE phone='5511900000002'")[0]["status"] == "skipped")
    run(S, "UPDATE niches SET outbound_text='Oi, {nome}! Posso te ajudar?', prompt='# PAPEL\nVocê é a Ana da Loja X.' WHERE id=?", blank)
    run(S, "DELETE FROM outbox")
    await S.dispatch(S.DispatchIn(niche_id=blank, lines="5511900000003;Teo", consent=True, origem="lista de teste"), S.BackgroundTasks())
    for _ in range(2): await tick(S)
    check("preenchido o nicho, o envio sai e ganha a frase SAIR se faltar", len(harness.SENT) == 1 and "SAIR" in harness.SENT[0]["text"], harness.SENT)

    # ---------- API oficial ----------
    S.PROVIDER = "official"
    check("na API oficial só existe o número principal e não dá para adicionar", S.active_lines() == ["main"] and await err(S.lines_add({"label": "X"})) == 400)
    S.PROVIDER = "qr"

    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
