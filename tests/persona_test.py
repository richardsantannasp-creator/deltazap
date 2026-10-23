"""Nome do agente que dispara: {agente} na abertura e no prompt, por número ou por nicho, e o agente usa o mesmo nome na conversa."""
import asyncio, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
OUT = "Olá {nome}! Aqui é {agente}, assistente virtual da Vida Mais. Posso te fazer 3 perguntas? Se não quiser receber mensagens, responda SAIR."
def last_sdr(S, ph):
    with S.conn() as c:
        return c.execute("SELECT text FROM messages WHERE phone=? AND role='sdr' ORDER BY id DESC LIMIT 1", (ph,)).fetchone()["text"]
async def main():
    S = harness.load_server()
    base = dict(name="Planos de saúde", prompt="# PAPEL\nVocê é {agente}, SDR da Vida Mais.", outbound_text=OUT)
    # sem nome em lugar nenhum: bloqueia com mensagem clara
    await S.niche_update(1, S.NicheIn(**base))
    r = await S.dispatch_one(S.get_niche(1), "5521911110001", "Bia", "")
    check("abertura com {agente} sem nome definido não sai", "defina o nome do agente" in str(r) and not S.get_lead("5521911110001")["stage"] == "contatado", r)
    # nome do nicho
    await S.niche_update(1, S.NicheIn(**base, agent_name="Ana"))
    check("nome do nicho é guardado", S.get_niche(1)["agent_name"] == "Ana")
    r = await S.dispatch_one(S.get_niche(1), "5521911110002", "Bia", "")
    t = last_sdr(S, "5521911110002")
    check("abertura sai com o nome do nicho", r == "ok" and "Aqui é Ana," in t and "{agente}" not in t and "Bia" in t, (r, t))
    sysq = "\n".join(b["text"] for b in S.build_system(S.get_lead("5521911110002"), S.get_niche(1)))
    check("o prompt também usa o nome e o agente é instruído a se apresentar com ele", "Você é Ana, SDR" in sysq and "Nesta conversa você se chama Ana" in sysq, sysq[:400])
    # nome por número
    with S.conn() as c:
        c.execute("INSERT INTO lines(id,label,active,created) VALUES('comercial2','Comercial 2',1,?)", (time.time(),))
    harness.GWL["comercial2"] = {"state": "open", "me": "5521999991111"}
    await S.lines_put("comercial2", {"persona": "Carla!! <b>"})
    ls = [l for l in S.line_summary() if l["id"] == "comercial2"][0]
    check("nome do número é limpo de símbolos e aparece no resumo dos números", ls["persona"] == "Carla b", ls)
    r = await S.dispatch_one(S.get_niche(1), "5521977700033", "Caio", "", line="comercial2")
    t = last_sdr(S, "5521977700033")
    check("número com nome próprio sobrescreve o do nicho", r == "ok" and "Aqui é Carla b," in t, t)
    sysq = "\n".join(b["text"] for b in S.build_system(S.get_lead("5521977700033"), S.get_niche(1)))
    check("na conversa o lead desse número fala com a mesma persona", "Nesta conversa você se chama Carla b" in sysq and "Você é Carla b, SDR" in sysq)
    sysq = "\n".join(b["text"] for b in S.build_system(S.get_lead("5521911110002"), S.get_niche(1)))
    check("o lead do outro número continua com o nome do nicho", "se chama Ana" in sysq)
    await S.lines_put("comercial2", {"persona": ""})
    check("limpar o nome do número volta ao do nicho", S.agent_persona(S.get_niche(1), "comercial2") == "Ana")
    # variações usam {agente} também
    await S.niche_update(1, S.NicheIn(**base, agent_name="Ana", outbound_variants="Oi {nome}! Sou {agente}, assistente virtual da Vida Mais. Quer ver opções? Se não quiser receber mensagens, responda SAIR."))
    texts = []
    for i in range(4):
        await S.dispatch_one(S.get_niche(1), f"552191111010{i}", "Zé", "")
        texts.append(last_sdr(S, f"552191111010{i}"))
    check("variações também preenchem {agente}", all("{agente}" not in x and "Ana" in x for x in texts), texts)
    # copiar o nicho copia o nome
    c = await S.niche_create(S.NicheIn(name="Cópia", copy_from=1))
    check("copiar o nicho copia o nome do agente", S.get_niche(c["id"])["agent_name"] == "Ana")
    check("nome inválido é limpo", S.clean_persona("  Ana<script>  ") == "Anascript")
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
