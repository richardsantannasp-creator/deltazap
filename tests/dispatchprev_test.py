"""Prévia obrigatória do disparo e resumo diário com números e agentes."""
import asyncio, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
async def raises(coro):
    try: await coro; return None
    except Exception as e: return str(getattr(e, "detail", e))
async def main():
    S = harness.load_server()
    OUT = "Olá, {nome}! Aqui é {agente}, assistente virtual da Vida Mais. Posso te fazer 3 perguntas? Se não quiser receber mensagens, responda SAIR."
    await S.niche_update(1, S.NicheIn(name="Planos de saúde", prompt="Você é {agente}.", outbound_text=OUT, outbound_variants="Oi {nome}, sou {agente}, da Vida Mais (assistente virtual). Posso ajudar? Se não quiser receber mensagens, responda SAIR."))
    D = lambda **k: S.DispatchIn(**{"niche_id": 1, "lines": "", "consent": True, "origem": "formulário do site 10/2026", **k})
    # validações iguais às do disparo
    check("prévia exige consentimento e origem", "consentimento" in (await raises(S.dispatch_preview(D(lines="11999990001", consent=False)))) and "de onde veio" in (await raises(S.dispatch_preview(D(lines="11999990001", origem="x")))))
    # sem nome do agente: bloqueia
    r = await S.dispatch_preview(D(lines="11999990001;Ana"))
    check("sem nome do agente a prévia bloqueia e avisa", r["blocked"] and any("{agente}" in w for w in r["warnings"]), r["warnings"])
    await S.niche_update(1, S.NicheIn(name="Planos de saúde", prompt="Você é {agente}.", outbound_text=OUT, agent_name="Ana", outbound_variants="Oi {nome}, sou {agente}, da Vida Mais (assistente virtual). Posso ajudar? Se não quiser receber mensagens, responda SAIR."))
    S.suppress("5511999990003"); S.personal_add(["5511999990004"])
    with S.conn() as c:
        c.execute("INSERT INTO leads(phone,name,stage,created,niche_id,test,origin) VALUES('5511999990005','Já fala','qualificando',?,1,0,'ativo')", (time.time(),))
        c.execute("INSERT INTO outbox(phone,niche_id,name,created) VALUES('5511999990006',1,'Na fila',?)", (time.time(),))
    lines = "11999990001;Maria Souza;Padaria X\n11999990002\n11999990003;Saiu\n11999990004;Mãe\n11999990005;Já fala\n11999990006;Na fila\n11999990001;Maria repetida\nabc"
    n_leads0 = len(S.parse_lines(lines))
    r = await S.dispatch_preview(D(lines=lines))
    check("separa quem será enfileirado e o motivo de cada pulado", r["to_send"] == 2 and r["skipped"] == {"supressao": 1, "pessoal": 1, "em_conversa": 1, "ja_na_fila": 1}, r["skipped"])
    check("mensagens reais com nome, agente e SAIR; alterna abertura principal e variação", len(r["samples"]) == 2 and "Maria" in r["samples"][0]["text"] and "Aqui é Ana" in r["samples"][0]["text"] and "sou Ana" in r["samples"][1]["text"] and all("SAIR" in m["text"] for m in r["samples"]), r["samples"])
    check("telefone aparece mascarado", all("…" in m["phone"] for m in r["samples"]), r["samples"])
    check("avisa contato sem nome", any("sem nome" in w for w in r["warnings"]), r["warnings"])
    check("estima dias com o limite de hoje e a fila existente", r["daily_capacity"] > 0 and r["days"] >= 1 and r["backlog"] == 1, r)
    # a prévia não grava nada
    with S.conn() as c:
        q = c.execute("SELECT COUNT(*) n FROM outbox WHERE status='queued'").fetchone()["n"]
        lead = c.execute("SELECT 1 FROM leads WHERE phone='5511999990001'").fetchone()
    check("a prévia não enfileira nem cria lead", q == 1 and lead is None, (q, lead))
    # campo pendente
    await S.niche_update(1, S.NicheIn(name="Planos de saúde", prompt="Você é {agente}, da [EMPRESA].", outbound_text=OUT, agent_name="Ana"))
    r = await S.dispatch_preview(D(lines="11999990001;Maria"))
    check("campo [..] pendente bloqueia a prévia", r["blocked"] and any("[EMPRESA]" in w for w in r["warnings"]), r["warnings"])
    # resumo diário
    await S.niche_update(1, S.NicheIn(name="Planos de saúde", prompt="Você é {agente}.", outbound_text=OUT, agent_name="Ana"))
    with S.conn() as c:
        c.execute("INSERT INTO outbox(phone,niche_id,status,created,sent_at,line) VALUES('5511988880001',1,'sent',?,?, 'main')", (time.time(), time.time()))
        c.execute("INSERT INTO leads(phone,name,stage,created,niche_id,test,origin) VALUES('5511988880001','Resp','qualificando',?,1,0,'ativo')", (time.time(),))
        c.execute("INSERT INTO messages(phone,role,text,ts) VALUES('5511988880001','lead','oi',?)", (time.time(),))
    d = S.compute_digest()
    check("resumo traz a situação de cada número", "📱 Números:" in d and "Principal" in d and "enviados 1/" in d, d)
    check("resumo traz o desempenho por agente", "🤖 Por agente:" in d and "Planos de saúde: 1 enviados · 1 responderam" in d, d)
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
