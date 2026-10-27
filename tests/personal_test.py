"""Contatos pessoais: nunca recebem disparo nem resposta da IA; agenda do celular entra pelo conector; lista manual."""
import asyncio, os, sys, tempfile, time, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
class Req:
    def __init__(self, d): self.d = d
    async def json(self): return self.d
async def main():
    S = harness.load_server()
    S.GATEWAY_SECRET = "seg"
    with S.conn() as c:
        c.execute("UPDATE niches SET agent_name='Ana', outbound_text='Olá, {nome}! Aqui é {agente}, assistente virtual. Posso ajudar? Se não quiser receber mensagens, responda SAIR.' WHERE id=1")
        c.execute("UPDATE niches SET prompt=REPLACE(prompt,'[','(') WHERE id=1")
    # lista manual (com e sem 55, com e sem o 9)
    r = await S.personal_post(S.PersonalIn(lines="(21) 98888-7777\n5511977776666\nlixo"))
    check("lista manual aceita números e ignora lixo", r["added"] == 2, r)
    check("reconhece o número com e sem 55 e com e sem o 9º dígito", S.is_personal("5521988887777") and S.is_personal("552188887777") and S.is_personal("5511977776666") and not S.is_personal("5521911110000"))
    # só guarda hash
    with S.conn() as c:
        h = [r["h"] for r in c.execute("SELECT h FROM personal")]
    check("guarda só código, não o telefone", all("8888" not in x and len(x) == 64 for x in h))
    # disparo: pula
    r = await S.dispatch_one(S.get_niche(1), "5521988887777", "Mãe", "")
    check("disparo direto é recusado", "pessoal" in str(r) and S.get_lead("5521988887777") is None, r)
    # fila: ao proteger, o que estava na fila é cancelado
    with S.conn() as c:
        c.execute("INSERT INTO outbox(phone,niche_id,name,created) VALUES('5521966665555',1,'Tio',?)", (time.time(),))
    r = await S.personal_post(S.PersonalIn(lines="21966665555"))
    with S.conn() as c:
        st = c.execute("SELECT status FROM outbox WHERE phone='5521966665555'").fetchone()["status"]
    check("proteger cancela o que já estava na fila", r["canceled"] == 1 and st == "skipped", (r, st))
    # lista de disparo: mistura contatos
    class BG:
        def add_task(self, *a, **k): pass
    d = await S.dispatch(S.DispatchIn(niche_id=1, lines="5521911112222;Cliente\n5521988887777;Mãe", consent=True, origem="formulário do site 10/2026"), BG())
    check("importação pula os pessoais e enfileira os demais", d["queued"] == 1 and d["suppressed"] == 1, d)
    # mensagem recebida: sem lead, sem resposta
    n0 = len(harness.CALLS)
    await S.handle_incoming("5511977776666", "Amigo", "oi, tudo bem?", "w1", send=False)
    check("mensagem de contato pessoal é ignorada (sem lead e sem IA)", S.get_lead("5511977776666") is None and len(harness.CALLS) == n0)
    await S.handle_incoming("5521955554444", "Cliente novo", "quero um plano de saúde", "w2", send=False)
    check("quem não é pessoal continua sendo atendido", S.get_lead("5521955554444") is not None)
    # agenda do celular pelo conector
    with S.conn() as c:
        c.execute("INSERT OR IGNORE INTO leads(phone,name,stage,created,niche_id,test,origin) VALUES('5521933332222','Já é lead','contatado',?,1,0,'ativo')", (time.time(),))
    try:
        await S.gw_contacts(Req({"phones": ["5521900001111"]}), x_secret="errado"); bad = False
    except Exception: bad = True
    check("o conector precisa do segredo", bad)
    r = await S.gw_contacts(Req({"line": "main", "phones": ["5521900001111", "5521900002222", "5521933332222", "123"]}), x_secret="seg")
    check("agenda: entram os salvos; quem já conversou com o sistema e números inválidos ficam de fora", r["received"] == 2 and S.is_personal("5521900001111") and not S.is_personal("5521933332222"), r)
    st = await S.personal_get()
    check("painel mostra manual x agenda e a sincronização", st["count"]["manual"] >= 3 and st["count"]["agenda"] >= 2 and st["sync"]["main"]["n"] == 2, st)
    await S.handle_incoming("5521900001111", "Dentista", "confirmando sua consulta", "w3", send=False)
    check("contato da agenda que escreve não é respondido", S.get_lead("5521900001111") is None)
    # remover e desligar
    r = await S.personal_remove(S.PersonalIn(lines="21988887777"))
    check("remover da proteção funciona (com variantes)", r["removed"] >= 1 and not S.is_personal("5521988887777"), r)
    await S.personal_guard_put({"enabled": False})
    check("com a proteção desligada nada é bloqueado", not S.is_personal("5511977776666"))
    await S.personal_guard_put({"enabled": True})
    check("ao religar volta a proteger", S.is_personal("5511977776666"))
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
