"""Testa as regras de operação: aceite do risco do modo QR, aviso do operador, origem do consentimento, lista de supressão e direitos do titular (exportar/apagar)."""
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
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0
D = lambda S, lines, **kw: S.DispatchIn(niche_id=1, lines=lines, consent=True, **kw)

async def main():
    S = harness.load_server()
    await S.pacing_put({"min_delay": 1, "max_delay": 1, "batch_size": 50, "warmup": False, "daily_limit": 500, "reply_delay_min": 0, "reply_delay_max": 0,
                        "start_hour": 0, "end_hour": 24, "weekdays_only": False})
    bg = S.BackgroundTasks()

    # ---------- aceite do risco do modo QR ----------
    run(S, "DELETE FROM settings WHERE k='qr_ack'")
    a = await S.qr_ack_get()
    check("sem aceite: o painel pede o aceite e lista os termos", a["required"] and not a["accepted"] and len(a["terms"]) >= 5 and any("banido" in t for t in a["terms"]), a)
    check("sem aceite o servidor informa que está bloqueado", S.qr_blocked())
    await S.dispatch(D(S, "5511911110001;Ana", origem="formulário do site"), bg)
    harness.SENT.clear(); await tick(S)
    check("sem aceite a fila não envia nada", not harness.SENT and q(S, "SELECT status FROM outbox")[0]["status"] == "queued", harness.SENT)
    await S.handle_incoming("5511911110002", "Bia", "oi quero plano de saude", None, True)
    check("sem aceite a IA não responde (e não gasta com o Claude)", not [m for m in harness.SENT if m["to"] == "5511911110002"], harness.SENT)
    check("a mensagem do lead continua guardada", q(S, "SELECT COUNT(*) n FROM messages WHERE phone='5511911110002' AND role='lead'")[0]["n"] == 1)
    check("aceite exige marcar e informar o nome", await err(S.qr_ack_post({"accept": False, "name": "Fulano de Tal"})) == 400 and await err(S.qr_ack_post({"accept": True, "name": "Fu"})) == 400)
    await S.qr_ack_post({"accept": True, "name": "Maria da Silva"})
    a = await S.qr_ack_get()
    check("depois do aceite fica registrado com nome e data", a["accepted"] and a["name"] == "Maria da Silva" and a["ts"] and q(S, "SELECT 1 FROM lgpd_log WHERE action='aceite_qr'"))
    harness.SENT.clear(); await tick(S)
    check("com o aceite a fila volta a enviar", len(harness.SENT) == 1)
    S.set_setting("qr_ack", json.dumps({"version": 0, "name": "x", "ts": 1}))
    check("aceite de uma versão antiga dos termos não vale", S.qr_blocked())
    await S.qr_ack_post({"accept": True, "name": "Maria da Silva"})
    S.PROVIDER = "official"
    check("na API oficial o aceite não é exigido", not S.qr_blocked() and (await S.qr_ack_get())["accepted"] and await err(S.qr_ack_post({"accept": True, "name": "Maria da Silva"})) == 400)
    S.PROVIDER = "qr"

    # ---------- aviso do operador ----------
    S.NOTICE_FILE = S.Path(tempfile.mkdtemp()) / "aviso.json"
    check("sem arquivo não há aviso", (await S.operator_notice())["notice"] is None)
    S.NOTICE_FILE.write_text(json.dumps({"level": "warn", "text": "Sua assinatura venceu há 1 dia."}), encoding="utf-8")
    n = (await S.operator_notice())["notice"]
    check("aviso do operador aparece com nível e texto", n and n["level"] == "warn" and "venceu" in n["text"], n)
    S.NOTICE_FILE.write_text(json.dumps({"level": "x", "text": "ok", "until": time.time() - 5}), encoding="utf-8")
    check("aviso expirado some", (await S.operator_notice())["notice"] is None)
    S.NOTICE_FILE.write_text("{quebrado", encoding="utf-8")
    check("arquivo corrompido não derruba o painel", (await S.operator_notice())["notice"] is None)
    S.NOTICE_FILE.write_text(json.dumps({"level": "invalido", "text": "x" * 900}), encoding="utf-8")
    n = (await S.operator_notice())["notice"]
    check("nível inválido vira info e o texto é limitado", n["level"] == "info" and len(n["text"]) == 500)

    # ---------- origem do consentimento ----------
    run(S, "DELETE FROM outbox"); run(S, "DELETE FROM leads"); run(S, "DELETE FROM messages"); harness.SENT.clear()
    check("disparo sem origem do consentimento é recusado", await err(S.dispatch(D(S, "5511922220001;Caio"), bg)) == 400 and await err(S.dispatch(D(S, "5511922220001;Caio", origem="  ok "), bg)) == 400)
    r = await S.dispatch(D(S, "5511922220001;Caio\n5511922220002;Duda", origem="  Formulário  do site   em 10/2026 "), bg)
    check("com origem, entra na fila", r["queued"] == 2)
    await tick(S); await tick(S)
    l = S.get_lead("5511922220001")
    check("a origem fica gravada no lead (espaços normalizados) com a data", l["consent_origin"] == "Formulário do site em 10/2026" and l["consent_at"], l)
    check("o registro LGPD guarda o consentimento do disparo", q(S, "SELECT detail FROM lgpd_log WHERE action='consentimento'")[-1]["detail"].endswith("Formulário do site em 10/2026"))

    # ---------- supressão ----------
    await S.handle_incoming("5511922220001", "Caio", "SAIR", None, True)
    check("quem pede SAIR entra na lista de supressão (guardada como hash)", S.is_suppressed("5511922220001") and "5511922220001" not in json.dumps(q(S, "SELECT * FROM suppressed")))
    check("o número com e sem formatação é reconhecido", S.is_suppressed("+55 (11) 92222-0001"))
    r = await S.dispatch(D(S, "5511922220001;Caio de novo\n5511933330001;Edu", origem="lista nova do evento"), bg)
    check("um novo disparo ignora quem está na supressão", r["queued"] == 1 and r["suppressed"] == 1, r)
    check("só números suprimidos: o disparo é recusado", await err(S.dispatch(D(S, "5511922220001;Caio", origem="lista nova do evento"), bg)) == 400)
    run(S, "UPDATE leads SET stage='novo' WHERE phone='5511922220001'")
    run(S, "INSERT INTO outbox(phone,niche_id,name,created) VALUES('5511922220001',1,'Caio',?)", time.time())
    harness.SENT.clear()
    for _ in range(4): await tick(S)
    check("item antigo da fila para número suprimido não é enviado", not [m for m in harness.SENT if m["to"] == "5511922220001"] and q(S, "SELECT error FROM outbox WHERE phone='5511922220001' AND status='skipped'"), harness.SENT)
    n = (await S.lgpd_suppress({"lines": "11 94444-0001\n11944440002;Fulano\nlixo"}))["added"]
    check("lista de supressão manual aceita vários números e ignora lixo", n == 2 and S.is_suppressed("5511944440001") and (await S.lgpd_suppress({"lines": "11944440001"}))["added"] == 0)
    csv_ = "nome;whatsapp\nTeste;11944440001\n".encode()
    import base64
    r = await S.contacts_parse(S.ContactsIn(filename="x.csv", data=base64.b64encode(csv_).decode()))
    check("a planilha também avisa que o contato pediu para sair", r["valid"] == 0 and any("sair" in i["reason"] for i in r["issues"]), r)

    # ---------- exportar e apagar ----------
    ph = "5511955550001"
    S.upsert_lead(ph, "Gabi", "Loja X", 1); S.add_msg(ph, "lead", "meu CPF é 123"); S.add_msg(ph, "sdr", "ok")
    S.set_lead(ph, stage="qualificando", consent_origin="evento Y")
    S.store_file(ph, b"\xff\xd8\xff", "image/jpeg", "abc")
    run(S, "INSERT INTO crm_refs(phone,system,person_id,deal_id) VALUES(?,?,?,?)", ph, "pipedrive", "9", "8")
    S.log("webhook", f"{ph}: meu CPF é 123")
    run(S, "INSERT INTO usage(ts,kind,phone,niche_id) VALUES(?,?,?,1)", time.time(), "agente", ph)
    ex = await S.lead_export(ph)
    d = json.loads(ex.content)
    check("exportar devolve mensagens, arquivos, etapas, origem do consentimento e o CRM externo",
          len(d["mensagens"]) == 2 and d["arquivos"] and d["lead"]["consent_origin"] == "evento Y" and d["crm_externo"] and d["etapas"], list(d))
    check("exportar tem nome de arquivo e fica registrado (sem o número)", "dados-5511955550001.json" in ex.headers["Content-Disposition"] and ph not in json.dumps(q(S, "SELECT * FROM lgpd_log WHERE action='exportar'")))
    check("exportar lead inexistente dá 404", await err(S.lead_export("000")) == 404)
    up = S.UPLOADS / ph
    check("o arquivo recebido existe no disco antes de apagar", up.exists())
    r = await S.lead_delete(ph)
    check("apagar remove lead, mensagens, arquivos, etapas, CRM e eventos com o número",
          r["ok"] and r["crm_externo"] and not S.get_lead(ph) and not q(S, "SELECT 1 FROM messages WHERE phone=?", ph) and not q(S, "SELECT 1 FROM files WHERE phone=?", ph)
          and not q(S, "SELECT 1 FROM crm_refs WHERE phone=?", ph) and not q(S, "SELECT 1 FROM stage_events WHERE phone=?", ph) and not q(S, "SELECT 1 FROM events WHERE text LIKE ?", f"%{ph}%"), r)
    check("apagar remove a pasta de arquivos e mantém o custo sem o número", not up.exists() and q(S, "SELECT COUNT(*) n FROM usage WHERE phone=?", ph)[0]["n"] == 0 and q(S, "SELECT COUNT(*) n FROM usage")[0]["n"] >= 1)
    check("apagar um lead comum NÃO o coloca na lista de supressão", not r["suppressed"] and not S.is_suppressed(ph))
    check("o registro da exclusão não guarda o número", q(S, "SELECT 1 FROM lgpd_log WHERE action='apagar'") and ph not in json.dumps(q(S, "SELECT * FROM lgpd_log")))
    r2 = await S.lead_delete("5511922220001")
    check("apagar quem pediu SAIR mantém a supressão (continua sem receber mensagens)", r2["suppressed"] and S.is_suppressed("5511922220001") and not S.get_lead("5511922220001"), r2)
    S.upsert_lead("5511966660001", "Zé", "", 1)
    r3 = await S.lead_delete("5511966660001", manter_supressao="1")
    check("o operador pode escolher manter a supressão ao apagar", r3["suppressed"] and S.is_suppressed("5511966660001"))
    check("apagar lead inexistente dá 404", await err(S.lead_delete("000")) == 404)
    g = await S.lgpd_get()
    check("painel LGPD mostra o total de suprimidos e o histórico", g["suppressed"] >= 4 and len(g["log"]) >= 4, g)

    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
