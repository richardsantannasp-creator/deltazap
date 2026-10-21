"""Testa custo do Claude, teste A/B, integração com CRM/agenda (webhook, CSV, .ics) e backup. Sem rede."""
import asyncio, hashlib, hmac, io, json, os, sqlite3, subprocess, sys, tempfile, time, zipfile
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
os.environ["BACKUP_KEEP"] = "3"
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

    # ================= custo =================
    await S.costs_config({"price_in": 1.0, "price_out": 5.0, "usd_brl": 5.0, "budget_month_brl": 0})
    await S.handle_incoming("5511977770001", "Ana", "oi, quero plano de saúde", None, True)
    u = q(S, "SELECT * FROM usage")
    check("cada chamada ao Claude registra tokens", len(u) == 1 and u[0]["inp"] == 1000 and u[0]["outp"] == 200 and u[0]["cache_read"] == 3000 and u[0]["kind"] == "agente", u)
    esperado = (1000 * 1.0 + 200 * 5.0 + 3000 * 0.1) / 1e6
    check("custo em USD: entrada + saída + cache a 10%", abs(u[0]["cost_usd"] - esperado) < 1e-9, (u[0]["cost_usd"], esperado))
    check("escrita de cache custa 125% da entrada", abs(S.cost_usd(0, 0, 0, 1_000_000, {"price_in": 1.0, "price_out": 5.0}) - 1.25) < 1e-9)
    c = S.compute_costs(30)
    check("relatório: R$ = USD x câmbio e separa leads de teste", abs(c["total_brl"] - esperado * 5.0) < 1e-6 and c["test_brl"] == 0 and c["calls"] == 1, c)
    r = await S.test_lead(S.TestIn(niche_id=1)); await S.handle_incoming(r["phone"], "", "oi quero plano", None, False)
    c2 = S.compute_costs(30)
    check("custo de lead de teste fica à parte", c2["test_brl"] > 0 and c2["by_kind"] and c2["by_niche"][0]["niche"], c2)
    check("custo por lead calculado", c["per_lead"] is not None and c["per_lead"] > 0, c)
    # orçamento: alerta 80% e 100%, bloqueio
    cfg = S.clean_cost_cfg({"budget_month_brl": esperado * 5.0 * 4 / 1, "budget_action": "bloquear", "usd_brl": 5.0})
    check("config de custo é limitada e validada", S.clean_cost_cfg({"usd_brl": -3, "budget_action": "xx"})["usd_brl"] == 0.1 and S.clean_cost_cfg({"budget_action": "xx"})["budget_action"] in ("alertar", "bloquear"))
    await S.costs_config({"budget_month_brl": esperado * 5.0 * 2.5, "budget_action": "bloquear"})   # orçamento = 2,5 chamadas
    await S.alerts_put({"whatsapp_to": "21999991111"})
    harness.SENT.clear()
    await S.handle_incoming("5511977770001", "Ana", "e quanto custa?", None, True); await asyncio.sleep(0.2)     # 2 chamadas = 80%
    await S.handle_incoming("5511977770001", "Ana", "tem coparticipação?", None, True); await asyncio.sleep(0.2)  # 3 chamadas = 120%
    av = q(S, "SELECT kind FROM alerts WHERE kind='orcamento'")
    check("alertas de 80% e 100% do orçamento (cada um uma vez)", len(av) == 2, av)
    n_calls = len(q(S, "SELECT 1 FROM usage"))
    harness.SENT.clear()
    await S.handle_incoming("5511977770001", "Ana", "alô?", None, True)
    check("orçamento estourado com 'bloquear': IA não chama o Claude nem responde", len(q(S, "SELECT 1 FROM usage")) == n_calls and not [m for m in harness.SENT if m["to"] == "5511977770001"], harness.SENT)
    check("mensagem do lead continua salva", q(S, "SELECT 1 FROM messages WHERE phone='5511977770001' AND text='alô?'"))
    await S.costs_config({"budget_action": "alertar"})
    await S.handle_incoming("5511977770001", "Ana", "voltei", None, True)
    check("com 'alertar' a IA continua respondendo", len(q(S, "SELECT 1 FROM usage")) == n_calls + 1)
    await S.costs_config({"budget_month_brl": 0})

    # ================= A/B =================
    run(S, "UPDATE niches SET prompt_b='PROMPT_B_DIFERENTE: seja mais direta', ab_pct=50 WHERE id=1")
    vs = {}
    for i in range(200):
        p = f"551190000{i:04d}"; S.upsert_lead(p, "L", "", 1); vs[p] = S.get_lead(p)["variant"]
    nb = sum(1 for v in vs.values() if v == "B")
    check("divisão 50/50 fica perto da metade", 70 <= nb <= 130, nb)
    p0 = next(iter(vs)); run(S, "DELETE FROM leads WHERE phone=?", p0); S.upsert_lead(p0, "L", "", 1)
    check("o mesmo telefone cai sempre na mesma variante", S.get_lead(p0)["variant"] == vs[p0])
    lb = next(p for p, v in vs.items() if v == "B"); la = next(p for p, v in vs.items() if v == "A")
    sb = S.build_system(S.get_lead(lb), S.get_niche(1))[0]["text"]; sa = S.build_system(S.get_lead(la), S.get_niche(1))[0]["text"]
    check("lead B usa o prompt B e lead A usa o prompt A", "PROMPT_B_DIFERENTE" in sb and "PROMPT_B_DIFERENTE" not in sa)
    run(S, "UPDATE niches SET ab_pct=0 WHERE id=1"); S.upsert_lead("5511900099991", "Z", "", 1)
    check("ab_pct=0 desliga o teste (todos A)", S.get_lead("5511900099991")["variant"] == "A")
    run(S, "UPDATE niches SET ab_pct=100, prompt_b='' WHERE id=1"); S.upsert_lead("5511900099992", "Z", "", 1)
    check("sem prompt B preenchido não há teste", S.get_lead("5511900099992")["variant"] == "A")
    # estatística
    check("p-valor: 20/100 vs 40/100 é significativo", S._p_two_prop(20, 100, 40, 100) < 0.01)
    check("p-valor: 20/100 vs 22/100 não é significativo", S._p_two_prop(20, 100, 22, 100) > 0.5)
    check("p-valor protege contra divisão por zero", S._p_two_prop(0, 0, 1, 1) is None and S._p_two_prop(0, 10, 0, 10) is None)
    for t in ("leads", "messages", "stage_events", "usage"): run(S, f"DELETE FROM {t}")
    run(S, "UPDATE niches SET prompt_b='B', ab_pct=50 WHERE id=1")
    now = time.time()
    def mk(p, v, stages):
        S.upsert_lead(p, "x", "", 1); S.set_lead(p, variant=v)
        S.add_msg(p, "sdr", "oi"); S.add_msg(p, "lead", "oi")
        for st in stages: S.set_lead(p, stage=st)
    for i in range(40): mk(f"5511800{i:05d}", "A", ["qualificando"] + (["qualificado"] if i < 8 else []))
    for i in range(40): mk(f"5511801{i:05d}", "B", ["qualificando"] + (["qualificado"] if i < 24 else []))
    ab = S.compute_ab(1, 30)
    check("A/B: contagens por variante", ab["A"]["leads"] == 40 and ab["B"]["leads"] == 40 and ab["A"]["qualificados"] == 8 and ab["B"]["qualificados"] == 24, ab)
    check("A/B: veredito aponta B quando é bem melhor", "prompt B" in ab["verdict"] and ab["p_qualificados"] < 0.05, ab["verdict"])
    run(S, "DELETE FROM leads WHERE phone LIKE '5511801%' AND phone > '551180100020'")
    check("A/B: amostra pequena pede mais leads", "Amostra pequena" in S.compute_ab(1, 30)["verdict"])
    check("endpoint /api/ab", (await S.ab_results(1, 30))["niche_id"] == 1)
    try: await S.ab_results(999, 30); check("A/B: nicho inexistente dá 404", False)
    except harness.HTTPException as e: check("A/B: nicho inexistente dá 404", e.status_code == 404)
    t = await S.test_lead(S.TestIn(niche_id=1, variant="B"))
    check("lead de teste pode forçar a variante B", S.get_lead(t["phone"])["variant"] == "B")
    nid = (await S.niche_create(S.NicheIn(name="Cópia", copy_from=1)))["id"]
    check("duplicar nicho copia o prompt B mas não o teste", S.get_niche(nid)["prompt_b"] == "B" and S.get_niche(nid)["ab_pct"] == 0)
    await S.niche_update(1, S.NicheIn(name="Planos de saúde", prompt="x", prompt_b="B", ab_pct=500))
    check("ab_pct é limitado a 0-100", S.get_niche(1)["ab_pct"] == 100)
    run(S, "UPDATE niches SET ab_pct=0 WHERE id=1")

    # ================= CRM / webhook =================
    for t_ in ("leads", "messages", "stage_events"): run(S, f"DELETE FROM {t_}")
    await S.integrations_put({"url": "https://crm.example/hook", "secret": "segredo123", "events": ["encaminhado", "ganho"]})
    S.upsert_lead("5511966660001", "Carla", "Loja X", 1)
    S.set_lead("5511966660001", bant=json.dumps({"temperatura": "quente", "resumo_encaminhamento": "Casal, Campinas"}), stage="encaminhado"); await asyncio.sleep(0.3)
    r = await harness.control(S, "GET", "/__test/crm", b"")
    evs = json.loads(r[2])
    check("evento 'encaminhado' chega ao CRM com os dados do lead", len(evs) == 1 and json.loads(evs[0]["body"])["event"] == "lead.encaminhado" and json.loads(evs[0]["body"])["lead"]["summary"] == "Casal, Campinas", evs)
    sig = evs[0]["headers"]["X-SDR-Signature"]
    check("assinatura HMAC-SHA256 confere com o corpo", sig == "sha256=" + hmac.new(b"segredo123", evs[0]["body"].encode(), hashlib.sha256).hexdigest())
    check("cabeçalho X-SDR-Event presente", evs[0]["headers"]["X-SDR-Event"] == "lead.encaminhado")
    S.set_lead("5511966660001", stage="qualificando"); await asyncio.sleep(0.2)
    check("etapas não marcadas não são enviadas", len(json.loads((await harness.control(S, "GET", "/__test/crm", b""))[2])) == 1)
    await S.set_outcome("5511966660001", S.OutcomeIn(outcome="ganho")); await asyncio.sleep(0.3)
    evs = json.loads((await harness.control(S, "GET", "/__test/crm", b""))[2])
    check("resultado 'ganho' também vai ao CRM", len(evs) == 2 and json.loads(evs[1]["body"])["event"] == "lead.ganho" and json.loads(evs[1]["body"])["lead"]["outcome"] == "ganho")
    S.upsert_lead("5511966660002", "Teste", "", 1, test=1); S.set_lead("5511966660002", stage="encaminhado"); await asyncio.sleep(0.2)
    check("lead de teste nunca vai ao CRM", len(json.loads((await harness.control(S, "GET", "/__test/crm", b""))[2])) == 2)
    check("log de entregas registrado", len(q(S, "SELECT 1 FROM crm_log WHERE status='ok'")) == 2)
    g = await S.integrations_get()
    check("o segredo nunca volta para a tela", g["has_secret"] and "secret" not in g and "segredo123" not in json.dumps(g))
    await S.integrations_put({"url": "https://crm.example/falha", "events": ["encaminhado"]})
    n0 = len(json.loads((await harness.control(S, "GET", "/__test/crm", b""))[2]))
    S.upsert_lead("5511966660003", "Dani", "", 1); S.set_lead("5511966660003", stage="encaminhado"); await asyncio.sleep(0.4)
    evs = json.loads((await harness.control(S, "GET", "/__test/crm", b""))[2])
    check("falha do CRM: 3 tentativas e erro registrado", len(evs) - n0 == 3 and q(S, "SELECT status,detail FROM crm_log ORDER BY id DESC LIMIT 1")[0]["status"] == "erro", len(evs) - n0)
    check("segredo mantido ao salvar sem informar um novo", (await S.integrations_get())["has_secret"])
    try: await S.integrations_put({"url": "ftp://x"}); check("URL inválida é recusada", False)
    except harness.HTTPException as e: check("URL inválida é recusada", e.status_code == 400)
    await S.integrations_put({"url": "https://crm.example/ok"})
    tr = await S.integrations_test()
    check("botão de teste entrega e informa o resultado", tr["ok"] and "HTTP 200" in tr["detail"], tr)
    await S.integrations_put({"url": ""})
    S.set_lead("5511966660003", stage="ganho_x"); await asyncio.sleep(0.2)

    # ================= exportação CSV =================
    S.upsert_lead("5511966660009", "=HYPERLINK(\"http://x\")", "A;B", 1)
    S.set_lead("5511966660009", bant=json.dumps({"temperatura": "morno"}))
    res = await S.export_leads(0)
    txt = res.content
    import csv as _csv
    rows = list(_csv.reader(io.StringIO(txt.lstrip("﻿")), delimiter=";"))
    check("CSV: BOM, separador ';' e cabeçalho", txt.startswith("﻿") and rows[0][:3] == ["telefone", "nome", "empresa"])
    dangerous = [r for r in rows if r[0] == "5511966660009"][0]
    check("CSV: neutraliza fórmulas (=...) e preserva ';' no texto", dangerous[1].startswith("'=") and dangerous[2] == "A;B", dangerous)
    check("CSV: leads de teste não saem", not any(r[0] == "5511966660002" for r in rows))

    # ================= agenda (.ics) =================
    P = S.parse_meeting
    import datetime as dt
    check("data: formato AAAA-MM-DD HH:MM", P("2026-10-21 15:30") == dt.datetime(2026, 10, 21, 15, 30))
    check("data: formato DD/MM/AAAA às HHhMM", P("21/10/2026 às 9h30") == dt.datetime(2026, 10, 21, 9, 30) and P("5/1/2027, 14:00") == dt.datetime(2027, 1, 5, 14, 0))
    check("data: texto livre/ inválida vira None", P("amanhã de tarde") is None and P("2026-13-45 10:00") is None and P("") is None and P(None) is None)
    S.set_lead("5511966660009", meeting="2026-10-21 15:30", stage="reuniao_agendada")
    ics = (await S.meeting_ics("5511966660009")).content
    check("ICS: horário de Brasília convertido para UTC (15:30 -> 18:30Z)", "DTSTART:20261021T183000Z" in ics and "DTEND:20261021T190000Z" in ics, ics)
    check("ICS: estrutura, CRLF e escapes", ics.startswith("BEGIN:VCALENDAR\r\n") and ics.rstrip().endswith("END:VCALENDAR") and "SUMMARY:Atendimento: =HYPERLINK" in ics and "WhatsApp: +5511966660009" in ics)
    check("ICS: linhas dobradas em 75 bytes", all(len(l.encode()) <= 75 for l in ics.split("\r\n")))
    S.set_lead("5511966660009", meeting="quando puder")
    try: await S.meeting_ics("5511966660009"); check("ICS: data ilegível dá erro claro", False)
    except harness.HTTPException as e: check("ICS: data ilegível dá erro claro", e.status_code == 404 and "AAAA-MM-DD" in e.detail)
    L = [l for l in await S.leads() if l["phone"] == "5511966660009"][0]
    check("lista de leads traz meeting_start", "meeting_start" in L and L["meeting_start"] is None)
    S.set_lead("5511966660009", meeting="2026-10-21 15:30")
    check("meeting_start preenchido quando a data é entendida", [l for l in await S.leads() if l["phone"] == "5511966660009"][0]["meeting_start"] == "2026-10-21T15:30")
    check("a ferramenta agendar_reuniao pede o formato AAAA-MM-DD HH:MM", any(t["name"] == "agendar_reuniao" and "AAAA-MM-DD" in t["description"] for t in S.TOOLS))

    # ================= backup =================
    os.makedirs(S.UPLOADS / "5511966660001", exist_ok=True)
    (S.UPLOADS / "5511966660001" / "multa.jpg").write_bytes(b"\xff\xd8fake")
    name = await S.backups_create()
    name = name["name"]
    z = zipfile.ZipFile(S.BACKUP_DIR / name)
    check("backup: zip com banco, anexos e LEIA-ME", {"sdr.db", "LEIA-ME.txt"} <= set(z.namelist()) and any(n.startswith("uploads/") and n.endswith("multa.jpg") for n in z.namelist()), z.namelist())
    tmp = tempfile.mkdtemp(); z.extract("sdr.db", tmp)
    cn = sqlite3.connect(os.path.join(tmp, "sdr.db"))
    check("backup: banco íntegro e com os leads", cn.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and cn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] >= 1)
    cn.close()
    check("backup: não inclui .env nem sessão do WhatsApp", not any(".env" in n or "auth" in n for n in z.namelist()))
    check("backup: permissão restrita (0600)", oct((S.BACKUP_DIR / name).stat().st_mode & 0o777) == "0o600")
    for _ in range(4): await S.backups_create()
    lst = (await S.backups_list())
    check("backup: mantém só os N mais recentes (3)", len(lst["items"]) == 3, [i["name"] for i in lst["items"]])
    check("backup: nomes sem colisão no mesmo segundo", len({i["name"] for i in lst["items"]}) == 3)
    for bad in ("../../etc/passwd", "sdr.db", "sdr-20260101-000000.zip.exe", "x.zip"):
        try: await S.backups_download(bad); check("download recusa nome inválido: " + bad, False)
        except harness.HTTPException as e: check("download recusa nome inválido: " + bad, e.status_code == 404)
    check("download de backup válido", (await S.backups_download(lst["items"][0]["name"])).path.endswith(".zip"))
    run(S, "DELETE FROM settings WHERE k='last_backup'")
    check("backup automático roda quando passou 24 h", await S.maybe_backup() is not None)
    check("backup automático não repete dentro de 24 h", await S.maybe_backup() is None)
    S.BACKUP_AUTO = False; run(S, "UPDATE settings SET v='0' WHERE k='last_backup'")
    check("BACKUP_AUTO=0 desliga o automático", await S.maybe_backup() is None); S.BACKUP_AUTO = True
    # restauração
    dest = tempfile.mkdtemp()
    shutil_db = os.path.join(dest, "sdr.db"); open(shutil_db, "wb").write(b"banco antigo")
    r = subprocess.run([sys.executable, os.path.join(harness.ROOT, "restore_backup.py"), str(S.BACKUP_DIR / lst["items"][0]["name"]), dest], capture_output=True, text=True)
    cn = sqlite3.connect(os.path.join(dest, "sdr.db"))
    check("restauração devolve banco íntegro e anexos", r.returncode == 0 and cn.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and os.path.exists(os.path.join(dest, "uploads", "5511966660001", "multa.jpg")), r.stdout + r.stderr)
    cn.close()
    check("restauração guarda o banco anterior", any(f.startswith("sdr.db.antes-da-restauracao-") for f in os.listdir(dest)))
    evil = os.path.join(dest, "evil.zip")
    with zipfile.ZipFile(evil, "w") as ez: ez.writestr("sdr.db", "x"); ez.writestr("../../fora.txt", "x")
    r = subprocess.run([sys.executable, os.path.join(harness.ROOT, "restore_backup.py"), evil, dest], capture_output=True, text=True)
    check("restauração recusa zip com caminho malicioso", r.returncode != 0 and "suspeito" in (r.stdout + r.stderr))
    h = await S.health()
    check("/health responde ok sem dados pessoais", h["ok"] is True and set(h) == {"ok", "uptime_s"})

    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
