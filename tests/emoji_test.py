"""Emojis do agente: nível por nicho entra nas instruções; valores inválidos viram «moderado»; cópia de nicho mantém."""
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
def systext(S, nid):
    S.upsert_lead("5521977771111", "Ana", niche_id=nid)
    blocks = S.build_system(S.get_lead("5521977771111"), S.get_niche(nid))
    return "\n".join(b["text"] for b in blocks)
async def main():
    S = harness.load_server()
    check("padrão do nicho: moderado", S.get_niche(1)["emoji"] == "moderado")
    t = systext(S, 1)
    check("moderado: instrui 1 ou 2 emojis, espelhar o lead e responder aos emojis dele", "# EMOJIS" in t and "1 ou 2 emojis" in t and "Espelhe o lead" in t and "👍 = concordou" in t, t[-600:])
    check("regras de segurança: nada em assunto sério e nunca emoji sozinho", "assunto sério" in t and "nunca vai sozinho" in t)
    base = dict(name="Planos de saúde", prompt="x", outbound_text="y SAIR")
    for lvl, frag in (("nenhum", "Não use emojis"), ("pouco", "no máximo 1 emoji"), ("bastante", "2 a 3 por mensagem")):
        await S.niche_update(1, S.NicheIn(**base, emoji=lvl))
        t = systext(S, 1)
        check(f"nível {lvl}", S.get_niche(1)["emoji"] == lvl and frag in t, t[-400:])
    await S.niche_update(1, S.NicheIn(**base, emoji="nenhum"))
    check("nenhum: ainda entende os emojis que o lead manda", "entenda o sentido" in systext(S, 1))
    await S.niche_update(1, S.NicheIn(**base, emoji="exagerado"))
    check("valor inválido vira moderado", S.get_niche(1)["emoji"] == "moderado")
    await S.niche_update(1, S.NicheIn(**base, emoji="pouco"))
    c = await S.niche_create(S.NicheIn(name="Cópia", copy_from=1))
    check("copiar nicho mantém o nível de emojis", S.get_niche(c["id"])["emoji"] == "pouco")
    n2 = await S.niche_create(S.NicheIn(name="Novo", prompt="x", outbound_text="y SAIR", emoji="bastante"))
    check("nicho novo guarda o nível escolhido", S.get_niche(n2["id"])["emoji"] == "bastante")
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
