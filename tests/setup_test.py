"""Assistente de primeira configuração: lista do que falta e rascunho do agente por IA (revisar antes de aplicar)."""
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
async def main():
    S = harness.load_server()
    await S.niche_update(1, S.NicheIn(name="Planos de saúde", prompt="Você é {agente}, SDR. [NOME DA EMPRESA]", outbound_text=""))
    r = await S.setup_status()
    ids = {i["id"]: i for i in r["items"]}
    check("lista aponta o que falta (abertura, campos [..], nome do agente)", not ids["opening"]["ok"] and not ids["niche_fill"]["ok"] and not ids["agent_name"]["ok"] and not r["ready"], ids)
    check("itens opcionais não contam no total", r["total"] == sum(1 for i in r["items"] if i["required"]) and not ids["variants"]["required"], r)
    # rascunho: não salva sozinho, sempre com SAIR
    try:
        await S.setup_draft(1, S.SetupDraftIn(empresa="", oferta="x")); ok = False
    except Exception: ok = True
    check("sem empresa/oferta é recusado", ok)
    d = await S.setup_draft(1, S.SetupDraftIn(empresa="Vida Mais", oferta="planos de saúde no RJ", agente="Ana!!"))
    check("rascunho traz abertura e 3 variações, todas com SAIR", "SAIR" in d["opening"] and len(d["variants"]) == 3 and all("SAIR" in v for v in d["variants"]) and d["agent_name"] == "Ana", d)
    check("gerar não salva", S.get_niche(1)["outbound_text"] == "")
    # a instrução proíbe inventar fatos
    check("o pedido à IA proíbe inventar preço/prazo", any("NÃO invente" in c.get("system", "") for c in harness.CALLS if c["kind"] == "rascunho"))
    await S.setup_apply(1, S.SetupApplyIn(opening=d["opening"], variants=d["variants"], agent_name=d["agent_name"]))
    n = S.get_niche(1)
    check("aplicar grava abertura, variações e nome", n["outbound_text"] == d["opening"] and len(S.parse_variants(n["outbound_variants"])) == 3 and n["agent_name"] == "Ana", n)
    check("o prompt não foi tocado", n["prompt"].startswith("Você é {agente}"))
    r = await S.setup_status(); ids = {i["id"]: i for i in r["items"]}
    check("itens de abertura, nome e variações ficam ok; [NOME DA EMPRESA] continua pendente", ids["opening"]["ok"] and ids["agent_name"]["ok"] and ids["variants"]["ok"] and not ids["niche_fill"]["ok"], ids)
    # aplicar sem nome não apaga o existente
    await S.setup_apply(1, S.SetupApplyIn(opening=d["opening"], variants=[], agent_name=""))
    check("aplicar sem nome mantém o nome atual", S.get_niche(1)["agent_name"] == "Ana")
    try:
        await S.setup_apply(1, S.SetupApplyIn(opening="  ")); ok = False
    except Exception: ok = True
    check("abertura vazia é recusada", ok)
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
