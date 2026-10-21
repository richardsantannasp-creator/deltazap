"""Roteiros (menu de opções) e resposta fora do horário, antes da IA."""
import asyncio, os, sys, tempfile
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
    seg_10 = datetime(2026, 10, 19, 10, 0, tzinfo=TZ); seg_20 = datetime(2026, 10, 19, 20, 0, tzinfo=TZ)
    AI = []
    async def fake_agent(phone): AI.append(phone); return "resposta da IA"
    S.run_agent = fake_agent; S.qr_blocked = lambda: False
    async def say(phone, text, n):
        await S.handle_incoming(phone, "Teste", text, "w" + str(n) + phone, send=False)
    def last(phone, role="sdr"):
        r = q(S, "SELECT text FROM messages WHERE phone=? AND role=? ORDER BY id DESC LIMIT 1", phone, role); return r[0]["text"] if r else ""
    S.now_local = lambda: seg_10
    await S.hours_put({"enabled": True, "days": [["09:00", "18:00"]] * 5 + [None, None], "message": "Estamos fechados. Voltamos {volta}. Horário: {horario}"})
    tag = (await S.tags_get())["tags"][0]["name"]
    # ---------- cadastro e validação ----------
    check("sem roteiros a IA responde normalmente", (await say("5521955550001", "oi", 1)) is None and AI == ["5521955550001"])
    check("roteiro sem nome é recusado", await code(S.flows_post({"trigger": "first", "message": "x"})) == 400)
    check("gatilho inválido é recusado", await code(S.flows_post({"name": "a", "trigger": "zzz", "message": "x"})) == 400)
    check("palavra-chave exige palavras", await code(S.flows_post({"name": "a", "trigger": "keyword", "message": "x"})) == 400)
    check("opção de texto sem texto é recusada", await code(S.flows_post({"name": "a", "trigger": "first", "message": "x", "options": [{"label": "A", "action": "text"}]})) == 400)
    check("nicho inexistente é recusado", await code(S.flows_post({"name": "a", "trigger": "first", "message": "x", "options": [{"label": "A", "action": "niche", "value": "nao existe"}]})) == 400)
    check("etiqueta inexistente é recusada", await code(S.flows_post({"name": "a", "trigger": "first", "message": "x", "options": [{"label": "A", "action": "tag", "value": "nao existe"}]})) == 400)
    niche = q(S, "SELECT name FROM niches LIMIT 1")[0]["name"]
    r = await S.flows_post({"name": "Boas-vindas", "trigger": "first", "message": "Olá! Como posso ajudar?", "options": [
        {"label": "Quero uma cotação", "action": "niche", "value": niche}, {"label": "Falar com uma pessoa", "action": "handoff", "value": "Já vou chamar alguém."},
        {"label": "Horário", "action": "text", "value": "Atendemos de segunda a sexta."}, {"label": "Marcar interesse", "action": "tag", "value": tag}]})
    fid = r["id"]
    g = await S.flows_get()
    check("lista o roteiro com as opções", len(g["flows"]) == 1 and len(g["flows"][0]["options"]) == 4 and "first" in g["triggers"])
    # ---------- primeira mensagem ----------
    AI.clear(); p = "5521955550002"
    await say(p, "oi", 2)
    t = last(p)
    check("1ª mensagem envia o menu numerado", "Olá! Como posso ajudar?" in t and "1) Quero uma cotação" in t and "4) Marcar interesse" in t, t)
    check("a IA espera o contato escolher", AI == [] and S.get_lead(p)["flow_step"])
    await say(p, "3", 3)
    check("opção de texto responde o texto e não chama a IA", last(p) == "Atendemos de segunda a sexta." and AI == [] and not S.get_lead(p)["flow_step"])
    await say(p, "e o preço?", 4)
    check("depois do menu a conversa segue com a IA", AI == [p])
    # escolha por nome, fora de ordem
    p2 = "5521955550003"; AI.clear()
    await say(p2, "bom dia", 5); await say(p2, "falar com uma pessoa", 6)
    l = S.get_lead(p2)
    check("opção «chamar a equipe» abre a transferência", l["human"] == 1 and l["stage"] == "humano" and "Já vou chamar alguém." == last(p2) and AI == [], l)
    # niche + tag continuam com a IA
    p3 = "5521955550004"; AI.clear()
    await say(p3, "oi", 7); await say(p3, "1", 8)
    check("opção «mudar de nicho» troca o nicho e segue com a IA", AI == [p3])
    p4 = "5521955550005"; AI.clear()
    await say(p4, "oi", 9); await say(p4, "4", 10)
    check("opção «etiqueta» marca o lead e segue com a IA", len(q(S, "SELECT 1 FROM lead_tags WHERE phone=?", p4)) == 1 and AI == [p4])
    p5 = "5521955550006"; AI.clear()
    await say(p5, "oi", 11); await say(p5, "quanto custa o plano?", 12)
    check("resposta que não é opção cai na IA e limpa o menu", AI == [p5] and not S.get_lead(p5)["flow_step"])
    # ---------- palavra-chave ----------
    r2 = await S.flows_post({"name": "Preços", "trigger": "keyword", "keywords": "preço, valor", "message": "Nossos planos começam em R$ 99.", "stop_ai": False})
    p6 = "5521955550007"; AI.clear()
    await S.handle_incoming(p6, "X", "Qual o PREÇO?", "w13", send=False)
    check("palavra-chave (sem acento/maiúscula) dispara e a IA ainda responde", any("R$ 99" in m["text"] for m in q(S, "SELECT text FROM messages WHERE phone=? AND role='sdr'", p6)) and AI == [p6])
    # ---------- fora do horário ----------
    await S.flows_post({"name": "Fora do horário", "trigger": "ooh", "message": "Estamos fechados. Voltamos {volta}.", "stop_ai": True})
    S.now_local = lambda: seg_20
    p7 = "5521955550008"; AI.clear()
    await say(p7, "oi", 14)
    check("fora do horário responde o aviso (com {volta}) e segura a IA", "Voltamos 20/10 às 09:00" in last(p7) and AI == [], last(p7))
    await say(p7, "alguém aí?", 15)
    check("não repete o aviso dentro de 12 h", AI == [p7])
    S.now_local = lambda: seg_10; AI.clear(); p8 = "5521955550009"
    await say(p8, "oi", 16)
    check("dentro do horário o aviso não dispara", "Estamos fechados" not in last(p8))
    # ---------- editar / desativar / excluir ----------
    await S.flows_put(fid, {"name": "Boas-vindas", "trigger": "first", "message": "Oi!", "options": [], "active": False})
    p9 = "5521955550010"; AI.clear()
    await say(p9, "oi", 17)
    check("roteiro desativado não dispara", "Oi!" not in last(p9) and AI == [p9])
    check("editar roteiro inexistente: 404", await code(S.flows_put(9999, {"name": "a", "trigger": "first", "message": "x"})) == 404)
    await S.flows_del(fid); await S.flows_del(r2["id"])
    check("excluir roteiro", len((await S.flows_get())["flows"]) == 1)
    # ---------- auditoria ----------
    check("ações de roteiro têm rótulo na auditoria", S.audit_label("POST", "/api/flows")[0] == "Criou roteiro")
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
