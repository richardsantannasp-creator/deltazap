"""Etiquetas, mudança de etapa (quadro) e filtros: administrador, atendente e gestor."""
import asyncio, os, sys, tempfile, time
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
    t = await S.tags_get()
    check("já vem com etiquetas de partida", {x["name"] for x in t["tags"]} >= {"Quente", "Morno", "Frio", "Cliente", "Retornar"}, t["tags"])
    check("lista as etapas do quadro, em ordem", [k for k, _ in t["stages"]][:3] == ["novo", "contatado", "qualificando"] and len(t["stages"]) == 9)
    a = await S.tags_add(S.TagIn(name="  VIP  ", color="roxo"))
    check("cria etiqueta (nome limpo)", a["ok"] and q(S, "SELECT name,color FROM tags WHERE id=?", a["id"])[0] == {"name": "VIP", "color": "roxo"})
    check("nome repetido é recusado", await err(S.tags_add(S.TagIn(name="vip"))) in (0, 400) and await err(S.tags_add(S.TagIn(name="VIP"))) == 400)
    check("nome vazio é recusado", await err(S.tags_add(S.TagIn(name=" "))) == 400)
    b = await S.tags_add(S.TagIn(name="Outra", color="cor-inventada"))
    check("cor desconhecida vira cinza", q(S, "SELECT color FROM tags WHERE id=?", b["id"])[0]["color"] == "cinza")
    await S.tags_put(b["id"], S.TagIn(name="Parceiro", color="verde"))
    check("edita etiqueta", q(S, "SELECT name,color FROM tags WHERE id=?", b["id"])[0] == {"name": "Parceiro", "color": "verde"})
    check("editar etiqueta inexistente: 404", await err(S.tags_put(9999, S.TagIn(name="x"))) == 404)
    ids = {x["name"]: x["id"] for x in (await S.tags_get())["tags"]}
    S.upsert_lead("5521966660001", "Ana Souza", niche_id=1); S.upsert_lead("5521966660002", "Bia Lima", niche_id=1)
    r = await S.lead_tags_put("5521966660001", S.LeadTagsIn(tags=[ids["Quente"], ids["VIP"], ids["Quente"], 99999, "x"]))
    check("etiqueta o lead (ignora repetidas, inexistentes e inválidas)", sorted(r["tags"]) == sorted([ids["Quente"], ids["VIP"]]), r)
    L = {l["phone"]: l for l in await S.leads()}
    check("a lista de leads traz as etiquetas", sorted(L["5521966660001"]["tags"]) == sorted([ids["Quente"], ids["VIP"]]) and L["5521966660002"]["tags"] == [])
    check("etiquetar lead inexistente: 404", await err(S.lead_tags_put("5500000000000", S.LeadTagsIn(tags=[1]))) == 404)
    await S.lead_tags_put("5521966660001", S.LeadTagsIn(tags=[ids["Frio"]]))
    check("a nova lista substitui a anterior", q(S, "SELECT tag_id FROM lead_tags WHERE phone='5521966660001'") == [{"tag_id": ids["Frio"]}])
    tl = {x["name"]: x["leads"] for x in S.tag_list()}
    check("contagem de leads por etiqueta", tl["Frio"] == 1 and tl["VIP"] == 0)
    await S.tags_del(ids["Frio"])
    check("excluir etiqueta tira dos leads", not q(S, "SELECT 1 FROM lead_tags WHERE tag_id=?", ids["Frio"]) and all(ids["Frio"] not in l["tags"] for l in await S.leads()))
    check("excluir etiqueta remove os vínculos", not q(S, "SELECT 1 FROM lead_tags WHERE tag_id=?", ids["Frio"]))
    # ---------- quadro: mudar de etapa ----------
    r = await S.lead_stage("5521966660001", S.StageIn(stage="qualificado"))
    check("mover para outra etapa", r["ok"] and S.get_lead("5521966660001")["stage"] == "qualificado")
    check("o histórico de etapas (funil) registra a mudança", any(e["stage"] == "qualificado" for e in q(S, "SELECT * FROM stage_events WHERE phone='5521966660001'")))
    check("etapa desconhecida é recusada", await err(S.lead_stage("5521966660001", S.StageIn(stage="inventada"))) == 400)
    check("lead inexistente: 404", await err(S.lead_stage("5500000000000", S.StageIn(stage="novo"))) == 404)
    check("mover para a mesma etapa não muda nada", (await S.lead_stage("5521966660001", S.StageIn(stage="qualificado")))["ok"])
    # descartar = lista de supressão
    await S.lead_stage("5521966660002", S.StageIn(stage="descartado"))
    check("mover para Descartado coloca o contato na lista de supressão (nunca mais recebe)", S.is_suppressed("5521966660002"))
    # com a equipe
    S._agent_create(S.AgentIn(login="rita", name="Rita", password="abcdef"), 0)
    run(S, "UPDATE agents SET last_seen=?, available=1", time.time())
    S.upsert_lead("5521966660003", "Caio", niche_id=1)
    r = await S.lead_stage("5521966660003", S.StageIn(stage="humano"))
    L3 = S.get_lead("5521966660003")
    check("mover para 'Com a equipe' envia à fila e entrega ao atendente disponível", r.get("handoff") and L3["human"] == 1 and L3["stage"] == "humano" and L3["agent_id"] is not None, L3)
    await S.lead_stage("5521966660003", S.StageIn(stage="qualificando"))
    L3 = S.get_lead("5521966660003")
    check("tirar da equipe devolve a conversa à IA", L3["human"] == 0 and L3["agent_id"] is None and L3["stage"] == "qualificando", L3)
    # ---------- atendente ----------
    tr = (await S.agent_login(S.AgentLoginIn(login="rita", password="abcdef")))["token"]
    S.upsert_lead("5521966660004", "Duda", niche_id=1); S.set_lead("5521966660004", human=1, stage="humano", agent_id=q(S, "SELECT id FROM agents")[0]["id"])
    r = await S.agent_lead_tags("5521966660004", S.LeadTagsIn(tags=[ids["Quente"]]), x_token=tr)
    check("atendente etiqueta conversa dele", r["tags"] == [ids["Quente"]])
    al = await S.agent_leads(x_token=tr)
    check("a lista do atendente traz etiquetas e o catálogo", al["leads"][0]["tags"] == [ids["Quente"]] and any(x["name"] == "Quente" for x in al["tags"]), al)
    check("atendente não etiqueta conversa que não é dele", await err(S.agent_lead_tags("5521966660001", S.LeadTagsIn(tags=[1]), x_token=tr)) == 403)
    # ---------- gestor ----------
    await S.managers_add(S.ManagerIn(login="gil", name="Gil", password="senhaforte1"))
    tg = (await S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1")))["token"]
    run(S, "INSERT INTO lines(id,label,active,created,manager_id) VALUES('gil-1','Gil',1,?,1)", time.time())
    await S.handle_incoming("5521955550001", "Eva", "oi", "g1", line="gil-1")
    r = await S.gestor_lead_tags("5521955550001", S.LeadTagsIn(tags=[ids["Cliente"]]), x_token=tg)
    check("gestor etiqueta lead do número dele", r["tags"] == [ids["Cliente"]])
    check("gestor não etiqueta lead de outro (administrador)", await err(S.gestor_lead_tags("5521966660001", S.LeadTagsIn(tags=[1]), x_token=tg)) == 404)
    gl = await S.gestor_leads(x_token=tg)
    check("a lista do gestor traz etiquetas, catálogo e etapas", gl["leads"][0]["tags"] == [ids["Cliente"]] and gl["tags"] and len(gl["stages"]) == 9)
    await S.gestor_lead_stage("5521955550001", S.StageIn(stage="qualificado"), x_token=tg)
    check("gestor move lead do número dele de etapa", S.get_lead("5521955550001")["stage"] == "qualificado")
    check("gestor não move lead alheio", await err(S.gestor_lead_stage("5521966660001", S.StageIn(stage="novo"), x_token=tg)) == 404)
    # ---------- LGPD ----------
    S.erase_lead("5521955550001")
    check("apagar os dados do lead apaga as etiquetas dele", not q(S, "SELECT 1 FROM lead_tags WHERE phone='5521955550001'"))
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
