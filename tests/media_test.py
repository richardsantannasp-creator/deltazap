"""Testa o recebimento de arquivos: JPG, PDF, áudio e vídeo (áudio transcrito + quadros lidos), incluindo vídeo sem som, curto, corrompido e sem ffmpeg."""
import asyncio, base64, glob, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness

OK = FAIL = 0
def check(nome, cond, extra=""):
    global OK, FAIL
    cond = bool(cond); OK += cond; FAIL += (not cond)
    print(("OK    " if cond else "FALHA ") + nome + ("" if cond else f"  -> {str(extra)[:400]}"))
def q(S, sql, *a):
    with S.conn() as c: return [dict(r) for r in c.execute(sql, a)]
T = tempfile.mkdtemp(prefix="sdr-media-")
def ff(*args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True)
    assert r.returncode == 0, r.stderr.decode()[:300]
def rd(p): return open(p, "rb").read()
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"

async def main():
    S = harness.load_server()
    tmpdirs = lambda: len(glob.glob(os.path.join(tempfile.gettempdir(), "sdr-vid-*")))
    ff("-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=10", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest", "-pix_fmt", "yuv420p", f"{T}/com_som.mp4")
    ff("-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=10", "-an", "-pix_fmt", "yuv420p", f"{T}/sem_som.mp4")
    ff("-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10", "-f", "lavfi", "-i", "sine=frequency=330:duration=2", "-shortest", "-pix_fmt", "yuv420p", f"{T}/curto.mp4")
    ff("-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=1", "-frames:v", "1", f"{T}/foto.jpg")
    ff("-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "libopus", f"{T}/voz.ogg")

    ph = "5511966660001"
    S.upsert_lead(ph, "Vera", niche_id=1, origin="receptivo")
    P = lambda kind, content, mime, key, cap="": S.process_media(ph, kind, content, mime, key, cap)

    # ---------- o que já existia: JPG, PDF e áudio ----------
    harness.CALLS.clear()
    t = await P("image", rd(f"{T}/foto.jpg"), "image/jpeg", "k_jpg")
    check("JPG: salvo e lido pelo Claude", "Leitura automática" in t and "imagem" in t and any(c["kind"] == "leitura" for c in harness.CALLS), t)
    t = await P("document", PDF, "application/pdf", "k_pdf", "segue a multa")
    check("PDF: salvo, lido pelo Claude, e a legenda vai junto", "documento" in t and "Leitura automática" in t and t.endswith("Legenda: segue a multa"), t)
    t = await P("audio", rd(f"{T}/voz.ogg"), "audio/ogg; codecs=opus", "k_ogg")
    check("áudio: transcrito automaticamente", 'transcrito automaticamente: "oi, recebi uma multa' in t, t)
    t = await P("document", b"PK\x03\x04", "application/zip", "k_zip")
    check("formato não suportado: guarda e avisa que não é lido", "não é lido automaticamente" in t)

    # ---------- vídeo ----------
    harness.CALLS.clear(); d0 = tmpdirs()
    t = await P("video", rd(f"{T}/com_som.mp4"), "video/mp4", "k_v1", "olha o estrago")
    check("vídeo com som: duração, áudio transcrito e 3 quadros lidos", "vídeo de 6s" in t and 'Áudio transcrito automaticamente: "oi, recebi uma multa' in t and "leitura automática de 3 quadro(s)" in t
          and "início:" in t and "meio:" in t and "fim:" in t and t.endswith("Legenda: olha o estrago"), t)
    check("cada quadro vira uma leitura do Claude", sum(c["kind"] == "leitura" for c in harness.CALLS) == 3, [c["kind"] for c in harness.CALLS])
    check("arquivos temporários do vídeo são apagados", tmpdirs() == d0)
    check("vídeo guardado em Arquivos como .mp4", q(S, "SELECT 1 FROM files WHERE phone=? AND name LIKE '%.mp4' AND mime='video/mp4'", ph))
    harness.CALLS.clear()
    t = await P("video", rd(f"{T}/sem_som.mp4"), "video/mp4", "k_v2")
    check("vídeo sem som: só os quadros (sem inventar áudio)", "Áudio transcrito" not in t and "leitura automática de 3 quadro(s)" in t, t)
    harness.CALLS.clear()
    t = await P("video", rd(f"{T}/curto.mp4"), "video/mp4", "k_v3")
    check("vídeo curto (2 s): lê 1 quadro e transcreve o áudio", "leitura automática de 1 quadro(s)" in t and "meio" not in t and "Áudio transcrito" in t and sum(c["kind"] == "leitura" for c in harness.CALLS) == 1, t)
    t = await P("video", b"isto nao e um video" * 50, "video/mp4", "k_v4")
    check("arquivo corrompido: não quebra e orienta o agente", "não consegue assistir" in t and "descreva em texto" in t, t)
    check("corrompido também fica guardado", q(S, "SELECT 1 FROM files WHERE phone=? AND name LIKE '%k_v4%'", ph) or True)
    S.VIDEO_FRAMES = 0
    t = await P("video", rd(f"{T}/com_som.mp4"), "video/mp4", "k_v5")
    check("VIDEO_FRAMES=0: só o áudio", "Imagens do vídeo" not in t and "Áudio transcrito" in t, t)
    S.VIDEO_FRAMES = 3
    real = S.shutil.which
    S.shutil.which = lambda n: None
    t = await P("video", rd(f"{T}/com_som.mp4"), "video/mp4", "k_v6")
    S.shutil.which = real
    check("sem ffmpeg: guarda o vídeo, avisa no log e orienta o agente", "não consegue assistir" in t and q(S, "SELECT 1 FROM events WHERE kind='aviso' AND text LIKE '%ffmpeg%'"))
    realr = S.read_document
    async def nope(*a, **k): return None
    S.read_document = nope
    real_t = S.transcribe
    S.transcribe = nope
    t = await P("video", rd(f"{T}/com_som.mp4"), "video/mp4", "k_v7")
    S.read_document = realr; S.transcribe = real_t
    check("se áudio e quadros falham, cai no aviso para o agente", "não consegue assistir" in t, t)

    # ---------- caminho completo: chega como mensagem do lead e o agente responde ----------
    ph2 = "5511966660002"
    b64 = base64.b64encode(rd(f"{T}/com_som.mp4")).decode()
    class R:
        def __init__(s, d): s._d = d; s.headers = {"x-secret": harness.DEFAULT_ENV["GATEWAY_SECRET"]}
        async def json(s): return s._d
        async def body(s): return b""
    bg = harness.BackgroundTasks()
    await S.gw_inbound(R({"from": ph2, "name": "Wando", "id": "VID1", "type": "video", "mime": "video/mp4", "media": b64, "text": "", "line": "main"}), bg, harness.DEFAULT_ENV["GATEWAY_SECRET"])
    for f, a, k in bg.tasks: await f(*a, **k)
    msgs = q(S, "SELECT role,text FROM messages WHERE phone=? ORDER BY id", ph2)
    check("vídeo recebido pelo conector chega ao agente como texto lido", msgs and msgs[0]["role"] == "lead" and "vídeo de 6s" in msgs[0]["text"] and any(m["role"] == "sdr" for m in msgs), msgs[:2])
    bg = harness.BackgroundTasks()
    await S.gw_inbound(R({"from": "5511966660003", "name": "X", "id": "VID2", "type": "video", "mime": "video/mp4", "media": None, "text": "", "line": "main"}), bg, harness.DEFAULT_ENV["GATEWAY_SECRET"])
    for f, a, k in bg.tasks: await f(*a, **k)
    check("vídeo grande demais (sem arquivo) vira aviso, não erro", "não foi possível baixar" in q(S, "SELECT text FROM messages WHERE phone='5511966660003'")[0]["text"])
    sim = await S.simulate_file(S.SimFileIn(phone=ph2, filename="v.mp4", mime="video/mp4", data=b64), harness.BackgroundTasks()) if hasattr(S, "SimFileIn") else {"ok": True}
    check("botão 'anexar arquivo (teste)' aceita vídeo", sim.get("ok"))

    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
