"""Playbook de objeções: orientação por nicho entra no prompt, vem com métricas, copia com o nicho e valida entradas."""
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
def sysq(S, nid):
    S.upsert_lead("5521977772222", "Ana", niche_id=nid)
    return "\n".join(b["text"] for b in S.build_system(S.get_lead("5521977772222"), S.get_niche(nid)))
async def main():
    S = harness.load_server()
    check("sem playbook, o prompt não traz o bloco", "PLAYBOOK DE OBJEÇÕES" not in sysq(S, 1))
    d = await S.playbook_api_get(1)
    check("lista as 8 objeções com sugestão e métricas", len(d["items"]) == 8 and all(i["suggested"] and "leads" in i for i in d["items"]) and d["items"][0]["guidance"] == "", d["items"][:1])
    await S.playbook_api_put(S.PlaybookIn(niche_id=1, items=[S.PlaybookItem(key="preco", guidance="Pergunte o que  ele compara\\n e destaque a rede"), S.PlaybookItem(key="depois", guidance="")]))
    t = sysq(S, 1)
    check("orientação preenchida entra no prompt, a vazia não", "# PLAYBOOK DE OBJEÇÕES" in t and "Preço / achou caro: Pergunte o que ele compara" in t and "Deixou para depois" not in t, t[-800:])
    check("o bloco manda adaptar e não inventar valores", "não afirme preço, desconto ou prazo" in t)
    check("outro nicho não herda", "PLAYBOOK DE OBJEÇÕES" not in sysq(S, 2) if S.get_niche(2) else True)
    c = await S.niche_create(S.NicheIn(name="Cópia", copy_from=1))
    check("copiar o nicho copia o playbook", "Pergunte o que ele compara" in sysq(S, c["id"]))
    for bad in (S.PlaybookIn(niche_id=1, items=[S.PlaybookItem(key="xyz", guidance="a")]), S.PlaybookIn(niche_id=999, items=[])):
        try:
            await S.playbook_api_put(bad); ok = False
        except Exception as e:
            ok = True
        check("entrada inválida é recusada", ok)
    await S.playbook_api_put(S.PlaybookIn(niche_id=1, items=[S.PlaybookItem(key="preco", guidance="x" * 2000)]))
    check("orientação é limitada a 700 caracteres", len(S.playbook_get(1)["preco"]) == 700)
    await S.playbook_api_put(S.PlaybookIn(niche_id=1, items=[S.PlaybookItem(key="preco", guidance="")]))
    check("limpar tudo tira o bloco", "PLAYBOOK DE OBJEÇÕES" not in sysq(S, 1))
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
