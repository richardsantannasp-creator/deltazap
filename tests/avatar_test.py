"""Fotos de perfil no chat: contato e número do operador, cache, privacidade e apagamento."""
import asyncio, os, sys, tempfile
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
async def main():
    S = harness.load_server()
    P = harness.PHOTO
    S.PROVIDER = "qr"
    a, b, t = "5511977770001", "5511977770002", "5511977770003"
    S.upsert_lead(a, "Ana Souza", niche_id=1, origin="receptivo"); S.upsert_lead(b, "Beto", niche_id=1, origin="receptivo")
    S.upsert_lead(t, "Teste", niche_id=1, origin="ativo"); S.set_lead(t, test=1)
    P["have"].add(a)
    r = await S.avatar(a, "")
    check("contato com foto: devolve a imagem", r.media_type == "image/png" and r.content[:4] == b"\x89PNG", r)
    n = len(P["calls"]); await S.avatar(a, "")
    check("segunda chamada vem do cache (gateway não é consultado de novo)", len(P["calls"]) == n)
    try: await S.avatar(b, ""); ok = False
    except Exception as e: ok = getattr(e, "status_code", 0) == 404
    check("contato sem foto: 404 (o painel mostra as iniciais)", ok)
    n = len(P["calls"]); 
    try: await S.avatar(b, "")
    except Exception: pass
    check("ausência de foto também fica em cache", len(P["calls"]) == n)
    n = len(P["calls"])
    try: await S.avatar(t, "")
    except Exception: pass
    check("lead de teste não consulta o WhatsApp", len(P["calls"]) == n)
    n = len(P["calls"])
    try: await S.avatar("5511900000000", "")
    except Exception: pass
    check("número desconhecido não é consultado (privacidade)", len(P["calls"]) == n)
    r = await S.avatar("me", "main")
    check("foto do próprio número conectado (operador)", r.media_type == "image/png")
    S.set_setting("alerts", __import__("json").dumps({**S.get_alerts_cfg(), "whatsapp_to": "5521988880001"}))
    P["have"].add("5521988880001")
    r = await S.avatar("5521988880001", "")
    check("foto de quem recebe os avisos (corretor/equipe)", r.media_type == "image/png")
    # expira e renova
    with S.conn() as c: c.execute("UPDATE avatars SET fetched=? WHERE who=?", (0, a))
    n = len(P["calls"]); await S.avatar(a, "")
    check("cache vencido consulta de novo", len(P["calls"]) == n + 1)
    # gateway desconectado mantém a foto antiga
    with S.conn() as c: c.execute("UPDATE avatars SET fetched=? WHERE who=?", (0, a))
    harness.GW["state"] = "close"
    r = await S.avatar(a, "")
    check("gateway desconectado: mantém a foto que já tinha", r.media_type == "image/png")
    harness.GW["state"] = "open"
    S.PROVIDER = "official"
    S.upsert_lead("5511977770009", "Oficial", niche_id=1, origin="receptivo")
    try: await S.avatar("5511977770009", ""); ok = False
    except Exception as e: ok = getattr(e, "status_code", 0) == 404
    check("API oficial não entrega foto: 404 e iniciais", ok)
    S.PROVIDER = "qr"
    ex = await S.lead_export(a)
    check("exportação LGPD informa que há foto guardada", '"foto_de_perfil_guardada": true' in str(ex.content))
    S.erase_lead(a, False)
    check("apagar o contato apaga a foto", not q(S, "SELECT 1 FROM avatars WHERE who=?", a))
    print(f"\n{OK} ok, {FAIL} falha(s)"); sys.exit(1 if FAIL else 0)
asyncio.run(main())
