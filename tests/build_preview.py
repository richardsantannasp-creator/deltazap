"""Gera a página de PRÉVIA (dados fictícios, sem servidor) a partir do painel real: python tests/build_preview.py saida.html
Usa tests/preview_mock.js (servidor de mentira que roda no navegador) e tests/preview_head.txt (tema claro/escuro da prévia)."""
import sys, pathlib
T = pathlib.Path(__file__).resolve().parent
d = (T.parent / "dashboard.html").read_text(encoding="utf-8")
mock = (T / "preview_mock.js").read_text(encoding="utf-8")
head = (T / "preview_head.txt").read_text(encoding="utf-8")
def rep(old, new):
    global d
    assert d.count(old) == 1, f"trecho não encontrado (o painel mudou?): {old[:60]}"
    d = d.replace(old, new)
rep('<meta name="viewport" content="width=device-width, initial-scale=1">', '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">')
rep("<title>Painel SDR WhatsApp</title>", "<title>Prévia · Painel SDR WhatsApp</title>")
i = d.index(":root{--bg"); j = d.index("*{box-sizing", i)
d = d[:i] + head + d[j:]
rep('<span class="pill wait hide" id="pw">', '<span class="pill off">PRÉVIA · dados fictícios · não conecta ao WhatsApp</span><span class="pill wait hide" id="pw">')
rep('let T=localStorage.getItem("tok")||prompt("Token do painel (DASH_TOKEN):")||"";localStorage.setItem("tok",T);', mock + '\n</script><script>\nlet T="demo";')
rep('<img src="${c.qr}" alt="QR code"><div><b>Escaneie com o WhatsApp</b>', '<img src="${c.qr}" alt="QR code"><div><b style="color:#c7831a">PRÉVIA: este QR é só um desenho e não conecta. Use o painel real (localhost:8000).</b><br><b>Escaneie com o WhatsApp</b>')
out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "preview-sdr.html")
out.write_text(d, encoding="utf-8"); print("gerado:", out, len(d), "bytes")
