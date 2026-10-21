"""Teste de fumaça contra o SEU servidor de verdade (usa a chave real da Anthropic; não envia nada ao WhatsApp).
Uso:  python tests/smoke_real.py http://localhost:8000 SEU_DASH_TOKEN
Só usa a biblioteca padrão do Python."""
import base64, json, sys, time, urllib.request, urllib.error

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
TOKEN = sys.argv[2] if len(sys.argv) > 2 else ""
fails = 0

def call(path, body=None, method=None, token=TOKEN):
    rq = urllib.request.Request(BASE + path, method=method or ("POST" if body is not None else "GET"),
                                headers={"X-Token": token, "Content-Type": "application/json"},
                                data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(rq, timeout=60) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except ValueError: return e.code, {}

def check(name, cond, detail=""):
    global fails
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else f"  -> {detail}"))
    fails += 0 if cond else 1

st, _ = call("/api/status", token="errado"); check("API recusa token errado", st == 401, st)
st, status = call("/api/status"); check("API aceita o seu token", st == 200, f"{st} (confira o DASH_TOKEN)")
if st != 200: sys.exit(1)
print(f"      modelo: {status['model']} | modo: {status['provider']}")
st, niches = call("/api/niches"); check("nichos carregados", st == 200 and len(niches) >= 2, st)
nid = next((n["id"] for n in niches if "Limpa" in n["name"]), niches[0]["id"])
st, t = call("/api/test-lead", {"niche_id": nid, "mode": "receptivo"}); check("cria lead de teste", st == 200, t)
phone = t.get("phone", "")
call("/api/simulate", {"phone": phone, "text": "Oi, recebi uma multa de radar em São Paulo e o prazo vence dia 16"})
reply = ""
for _ in range(30):                                   # espera até 60 s pela resposta real do Claude
    time.sleep(2); _, msgs = call("/api/messages/" + phone)
    reply = next((m["text"] for m in msgs if m["role"] == "sdr"), "")
    if reply: break
check("o Claude respondeu (chave da Anthropic e modelo funcionando)", bool(reply), "sem resposta: veja o painel > log (ERRO) e a ANTHROPIC_API_KEY do .env")
if reply: print("      resposta:", reply[:160].replace("\n", " "))
st, s = call(f"/api/leads/{phone}/suggest", {}); check("sugestão de resposta", st == 200 and s.get("text"), s)
csv = base64.b64encode("nome;whatsapp\nAna Teste;11 99999-0001\nCurto;123\n".encode()).decode()
st, p = call("/api/contacts/parse", {"filename": "t.csv", "data": csv}); check("importa planilha", st == 200 and p.get("valid") == 1, p)
st, c = call("/api/pacing"); check("ritmo de envio", st == 200 and c.get("min_delay", 0) >= 20, c)
st, m = call("/api/metrics"); check("métricas", st == 200 and "risk" in m, m)
st, cn = call("/api/connection"); print(f"      conexão: {cn.get('provider')} / {cn.get('state')}")
check("conexão responde", st == 200, cn)
call("/api/leads/" + phone + "/takeover", {"human": True})
print(f"\n{'Tudo certo.' if not fails else str(fails) + ' falha(s).'} (o lead de teste fica no painel, marcado como 'teste')")
sys.exit(1 if fails else 0)
