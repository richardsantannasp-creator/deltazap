"""Materiais para enviar, janela de 24 h e novos tipos de mensagem recebida."""
import asyncio, os, sys, tempfile, base64, json
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
def b64(b): return base64.b64encode(b).decode()
async def expect(coro):
    try: await coro; return None
    except Exception as e: return e
async def main():
    S = harness.load_server(); S.PROVIDER = "qr"; harness.GW["state"] = "open"
    S.UPLOADS = S.Path(tempfile.mkdtemp(prefix="sdr-up-")); S.MAT_DIR = S.UPLOADS / "_materiais"
    nid = S.default_niche_id()
    pdf = b"%PDF-1.4 teste"
    r = await S.mat_add(S.MatIn(niche_id=nid, name="Catálogo 2026", descr="quando pedir preços", filename="cat.pdf", mime="application/pdf", data=b64(pdf)))
    check("cadastra PDF", r["ok"] and (S.MAT_DIR / q(S, "SELECT file FROM materials")[0]["file"]).read_bytes() == pdf)
    e = await expect(S.mat_add(S.MatIn(niche_id=nid, name="catálogo 2026", filename="x.pdf", mime="application/pdf", data=b64(pdf))))
    check("nome repetido é recusado", e is not None and "Já existe" in str(e.detail))
    e = await expect(S.mat_add(S.MatIn(niche_id=nid, name="Vírus", filename="a.exe", mime="application/x-msdownload", data=b64(b"MZ"))))
    check("formato perigoso é recusado", e is not None and "Formato" in str(e.detail))
    e = await expect(S.mat_add(S.MatIn(niche_id=nid, name="Grande", filename="g.pdf", mime="application/pdf", data=b64(b"0" * (S.MAT_MAX + 1)))))
    check("arquivo grande demais é recusado", e is not None and "grande" in str(e.detail))
    e = await expect(S.mat_add(S.MatIn(niche_id=nid, name="Sem tipo", filename="v.mp4", mime="application/octet-stream", data=b64(b"abc"))))
    check("tipo deduzido pela extensão quando o navegador não informa", e is None)
    # contexto e ferramentas
    niche = S.get_niche(nid) if hasattr(S, "get_niche") else q(S, "SELECT * FROM niches WHERE id=?", nid)[0]
    check("o agente enxerga os materiais e a ferramenta", "Catálogo 2026" in S.materials_context(niche) and any(t["name"] == "enviar_material" for t in S.tools_for(niche)))
    # envio (QR)
    S.upsert_lead("5521977770001", "Cliente", niche_id=nid)
    harness.MEDIA["sent"].clear()
    out = await S.send_material("5521977770001", {"nome": "catálogo 2026", "mensagem": "Segue"})
    check("envia pelo conector com tipo, nome e legenda", len(harness.MEDIA["sent"]) == 1 and harness.MEDIA["sent"][0]["kind"] == "document" and harness.MEDIA["sent"][0]["filename"] == "cat.pdf" and "enviado com sucesso" in out, harness.MEDIA["sent"])
    check("registra na conversa e conta o envio", q(S, "SELECT 1 FROM messages WHERE phone=? AND kind='material'", "5521977770001") and q(S, "SELECT sent FROM materials WHERE name='Catálogo 2026'")[0]["sent"] == 1)
    out = await S.send_material("5521977770001", {"nome": "Catálogo 2026"})
    check("não reenvia o mesmo material em 6 h", len(harness.MEDIA["sent"]) == 1 and "já foi enviado" in out)
    out = await S.send_material("5521977770001", {"nome": "Inventado"})
    check("material inexistente: o agente é instruído", "não encontrado" in out and len(harness.MEDIA["sent"]) == 1)
    # lead de teste não envia de verdade
    S.upsert_lead("5521977770002", "T", niche_id=nid, test=1); harness.MEDIA["sent"].clear()
    await S.send_material("5521977770002", {"nome": "Catálogo 2026"})
    check("lead de teste não dispara arquivo de verdade", not harness.MEDIA["sent"])
    # sem WhatsApp / falha
    S.upsert_lead("5521977770404", "Sem", niche_id=nid)
    out = await S.send_material("5521977770404", {"nome": "Catálogo 2026"})
    check("número sem WhatsApp: mensagem clara e sem registro de envio", "não tem WhatsApp" in out and not q(S, "SELECT 1 FROM material_sends WHERE phone=?", "5521977770404"))
    S.upsert_lead("5521977770003", "F", niche_id=nid); harness.MEDIA["fail"] = 1
    out = await S.send_material("5521977770003", {"nome": "Catálogo 2026"}); harness.MEDIA["fail"] = 0
    check("falha no envio: orienta a avisar que a equipe manda", "equipe envia" in out and not q(S, "SELECT 1 FROM material_sends WHERE phone=?", "5521977770003"))
    # API oficial: upload + janela de 24 h
    S.PROVIDER = "official"; S.WA_TOKEN = "tok"; S.WA_PHONE_ID = "123"; harness.MEDIA["graph"].clear()
    S.upsert_lead("5521977770005", "O", niche_id=nid)
    out = await S.send_material("5521977770005", {"nome": "Catálogo 2026"})
    g = harness.MEDIA["graph"]
    check("API oficial: sobe o arquivo e envia o documento com nome", len(g) == 2 and g[0]["url"].endswith("/media") and g[1]["json"]["type"] == "document" and g[1]["json"]["document"]["filename"] == "cat.pdf" and g[1]["json"]["document"]["id"] == "media_1", g)
    S.upsert_lead("5521977770006", "J", niche_id=nid); harness.MEDIA["window"] = 1
    out = await S.send_material("5521977770006", {"nome": "Catálogo 2026"})
    check("janela de 24 h vencida: não registra envio e avisa", "equipe envia" in out and not q(S, "SELECT 1 FROM material_sends WHERE phone=?", "5521977770006"))
    res = await S.reply_to("5521977770006", "Olá!", role="humano", humanize=False)
    check("texto fora da janela: retorna janela24h e marca a mensagem como falha", res == "janela24h" and q(S, "SELECT kind FROM messages WHERE phone=? ORDER BY id DESC", "5521977770006")[0]["kind"] == "falha", res)
    class B: text = "Oi, tudo bem?"
    e = await expect(S.manual_send("5521977770006", B())) if hasattr(S, "manual_send") else None
    if hasattr(S, "manual_send"):
        check("envio manual fora da janela: erro 409 explicando", e is not None and getattr(e, "status_code", 0) == 409 and "24 h" in str(e.detail), e)
    harness.MEDIA["window"] = 0
    # novos tipos recebidos (API oficial)
    t = S.describe_special("location", {"location": {"latitude": -23.5, "longitude": -46.6, "name": "Loja", "address": "Rua A"}})
    check("localização vira texto com link do mapa", "Loja" in t and "maps.google.com/?q=-23.5,-46.6" in t, t)
    t = S.describe_special("contacts", {"contacts": [{"name": {"formatted_name": "Maria"}, "phones": [{"phone": "+5511999990000"}]}]})
    check("contato compartilhado vira texto", "Maria" in t and "5511999990000" in t, t)
    check("resposta de botão vira o texto do botão", S.describe_special("interactive", {"interactive": {"button_reply": {"title": "Quero saber mais"}}}) == "Quero saber mais")
    # apagar dados do lead leva os registros de envio
    # api: desativar / apagar
    mid = q(S, "SELECT id FROM materials WHERE name='Catálogo 2026'")[0]["id"]
    await S.mat_edit(mid, {"active": False})
    check("material desativado some do agente", "Catálogo 2026" not in S.materials_context(niche) and "Catálogo 2026" not in json.dumps(S.tools_for(niche), ensure_ascii=False))
    await S.mat_del(mid)
    check("apagar remove o arquivo e os registros", not q(S, "SELECT 1 FROM materials WHERE id=?", mid))
    print(f"\n{OK} ok, {FAIL} falha(s)"); sys.exit(1 if FAIL else 0)
asyncio.run(main())
