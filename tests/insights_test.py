"""Aprender com conversas reais: relatório (onde somem, objeções, vencedoras, horários) e casos de teste reproduzidos."""
import asyncio, json, os, sys, tempfile, time
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
    S = harness.load_server(); S.PROVIDER = "qr"
    now = time.time(); H = 3600
    def mk(phone, stage, outcome, msgs, age=10 * 24 * H, name="Cliente"):
        S.upsert_lead(phone, name, niche_id=1); run(S, "UPDATE leads SET stage=?, outcome=?, created=? WHERE phone=?", stage, outcome, now - age - 100, phone)
        t = now - age
        for role, text in msgs:
            run(S, "INSERT INTO messages(phone,role,text,ts) VALUES(?,?,?,?)", phone, role, text, t); t += 60
    # objeção de preço, continuou e virou reunião
    mk("5521900000001", "reuniao_agendada", "", [("sdr", "Oi! Posso te ajudar?"), ("lead", "Quanto custa? Achei caro"), ("sdr", "Entendo! Posso te mostrar o que está incluso e ver se cabe no seu orçamento?"), ("lead", "pode sim, meu email é joao@exemplo.com"), ("sdr", "Perfeito, agendado.")])
    # preço, sumiu depois da nossa pergunta
    mk("5521900000002", "qualificando", "", [("sdr", "Oi!"), ("lead", "qual o preço?"), ("sdr", "Qual a sua cidade e quantas pessoas?")])
    mk("5521900000003", "qualificando", "", [("sdr", "Oi!"), ("lead", "valor?"), ("sdr", "Qual a sua cidade e quantas pessoas?")])
    # já tem, 3 mensagens e sumiu
    mk("5521900000004", "qualificando", "", [("lead", "já tenho plano"), ("sdr", "Entendi, está satisfeito?"), ("lead", "mais ou menos"), ("sdr", "O que mais incomoda?"), ("lead", "o preço"), ("sdr", "Posso comparar para você?")])
    # recente (não é sumiço ainda)
    mk("5521900000005", "qualificando", "", [("lead", "oi, quanto custa"), ("sdr", "Qual sua cidade?")], age=2 * H)
    # descartado e outro positivo (ganho) com 2 msgs
    mk("5521900000006", "descartado", "", [("lead", "não tenho interesse"), ("sdr", "Tudo bem!")])
    mk("5521900000007", "novo", "ganho", [("lead", "tenho interesse"), ("sdr", "Ótimo, qual produto?"), ("lead", "o ouro"), ("sdr", "fechado")])
    # sem resposta nenhuma
    mk("5521900000008", "contatado", "", [("sdr", "Oi!")])
    # lead de teste não conta
    S.upsert_lead("0111", "teste", niche_id=1, test=1)
    # disparos para os horários
    for i in range(6):
        run(S, "INSERT INTO outbox(phone,niche_id,status,sent_at,line,created) VALUES(?,?,?,?,?,?)", f"55219000000{i + 1:02d}", 1, "sent", now - 5 * 86400 + 0, "main", now)
    r = S.insights_report(1, 30)
    check("conta leads reais (sem os de teste) e quem respondeu", r["leads"] == 8 and r["replied"] == 7, (r["leads"], r["replied"]))
    check("conta os resultados positivos (reunião e ganho)", r["positive"] == 2, r["positive"])
    g = r["ghosted"]
    check("sumiram: só quem parou há mais de 72 h e não encerrou", g["total"] == 3, g)
    check("por nº de respostas do lead", g["by_replies"] == {"1": 2, "2": 0, "3": 1, "4+": 0}, g["by_replies"])
    check("a última pergunta do agente antes do sumiço é a mais repetida", g["last_agent_message"][0]["n"] == 2 and "cidade" in g["last_agent_message"][0]["text"], g["last_agent_message"])
    ob = {o["id"]: o for o in r["objections"]}
    check("objeção de preço: 5 leads, 1 continuou, 1 positivo", ob["preco"]["leads"] == 5 and ob["preco"]["positive"] == 1 and ob["preco"]["continued"] >= 1, ob.get("preco"))
    check("objeção «já tem» e «sem interesse» detectadas", ob["ja_tem"]["leads"] == 1 and ob["sem_interesse"]["leads"] == 1)
    ex = ob["preco"]["examples"]
    check("exemplo de resposta que funcionou, sem dados pessoais", ex and "Entendo" in ex[0]["reply"] and "joao@" not in json.dumps(ex), ex)
    check("ordenadas pelas mais frequentes", [o["leads"] for o in r["objections"]] == sorted([o["leads"] for o in r["objections"]], reverse=True))
    check("lista conversas vencedoras", {w["phone"] for w in r["winners"]} == {"5521900000001", "5521900000007"}, r["winners"])
    check("horários: só horas com pelo menos 5 envios", len(r["hours"]) >= 1 and all(h["sent"] >= 5 for h in r["hours"]), r["hours"])
    # ---------- casos de teste ----------
    check("caso de teste de lead inexistente: 404", await err(S.eval_case_add(S.CaseIn(phone="5500000000000"))) == 404)
    check("conversa com 1 mensagem do cliente: recusada", await err(S.eval_case_add(S.CaseIn(phone="5521900000002"))) == 400)
    a = await S.eval_case_add(S.CaseIn(phone="5521900000001", name="Preço virou reunião"))
    sc = json.loads(q(S, "SELECT script FROM eval_cases WHERE id=?", a["id"])[0]["script"])
    check("guarda só as falas do cliente, sem telefone e sem e-mail", a["ok"] and a["messages"] == 2 and "joao@" not in json.dumps(sc) and "[e-mail]" in json.dumps(sc) and "5521900000001" not in json.dumps(q(S, "SELECT * FROM eval_cases")), sc)
    ps = (await S.eval_personas())["personas"]
    check("o caso aparece entre os cenários da avaliação", any(p["id"] == f"caso_{a['id']}" and p.get("real") for p in ps))
    st = await S.insights_get(1, 30)
    check("a tela recebe a lista de casos", len(st["cases"]) == 1 and st["cases"][0]["name"] == "Preço virou reunião")
    # reprodução na avaliação (sem Claude para o cliente)
    harness.AGENT_HOOK["fn"] = lambda t, system: "Resposta do agente."
    pers = f"caso_{a['id']}"
    msg0 = await S.sim_lead_message(pers, S.get_niche(1), [], "x")
    msg1 = await S.sim_lead_message(pers, S.get_niche(1), [{"role": "lead", "text": msg0}, {"role": "sdr", "text": "r"}], "x")
    msg2 = await S.sim_lead_message(pers, S.get_niche(1), [{"role": "lead", "text": "a"}, {"role": "sdr", "text": "r"}, {"role": "lead", "text": "b"}], "x")
    check("o cliente simulado repete as falas reais, na ordem, e termina no fim", msg0.startswith("Quanto custa") and "[e-mail]" in msg1 and msg2 == "[FIM]", (msg0, msg1, msg2))
    r2 = await S.eval_run(S.EvalIn(niche_id=1, personas=[pers], turns=4, confirm_cost=True))
    for _ in range(400):
        if not S.EVAL_RUNNING["id"]: break
        await asyncio.sleep(0.05)
    res = await S.eval_get(r2["id"])
    check("a avaliação roda o caso real contra o agente atual", res["status"] == "done" and res["results"][0]["nome"].startswith("Caso real") and len(res["results"][0]["transcript"]) >= 2, res.get("results"))
    check("nada do caso fica no banco depois da avaliação", not q(S, "SELECT 1 FROM leads WHERE test=1 AND phone LIKE '5599%'"))
    check("limpar caso", (await S.eval_case_del(a["id"]))["ok"] and not q(S, "SELECT 1 FROM eval_cases"))
    check("caso apagado some dos cenários", not any(str(p["id"]).startswith("caso_") for p in (await S.eval_personas())["personas"]))
    check("rótulo na auditoria", S.audit_label("POST", "/api/eval/cases")[0].startswith("Criou caso"))
    check("nicho inexistente: 404", await err(S.insights_get(999, 30)) == 404)
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
