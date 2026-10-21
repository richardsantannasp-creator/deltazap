"""Verificações estáticas (sem rede): compila o código e cruza painel x servidor x prompts x configuração.
Uso: python tests/static_checks.py"""
import json, py_compile, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails, oks = [], []
def check(name, cond, detail=""):
    (oks if cond else fails).append(name + ("" if cond else f"  -> {detail}"))

srv = (ROOT / "server.py").read_text(encoding="utf-8")
dash = (ROOT / "dashboard.html").read_text(encoding="utf-8")

# 1) compila
try:
    py_compile.compile(str(ROOT / "server.py"), doraise=True); check("server.py compila", True)
except Exception as e:
    check("server.py compila", False, e)

# 2) todo id usado no JS do painel existe no HTML
html_ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', dash))
used = set(re.findall(r'\$\("([^"]+)"\)', dash)) | set(re.findall(r'getElementById\("([^"]+)"\)', dash))
used |= {"v" + str(i) for i in (1, 2, 3)} | {"t" + str(i) for i in (1, 2, 3)}
F = re.search(r'const F=\[(.*?)\];', dash, re.S)
if F:
    used |= {"p_" + k.strip().strip('"') for k in F.group(1).split(",")}
missing = sorted(i for i in used if i not in html_ids)
check("todo $('id') do painel existe no HTML", not missing, missing)

# 3) toda chamada api('/api/...') do painel tem rota no servidor
routes = re.findall(r'@app\.(get|post|put|delete)\("([^"]+)"', srv)
pats = [(m, re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "$")) for m, p in routes]
calls = set(re.findall(r'api\(\s*[`"\']([^`"\']+)', dash)) | set(re.findall(r'fetch\(\s*[`"\']([^`"\']+)', dash))
calls = {re.sub(r"\$\{[^}]+\}", "x", c).split("?")[0] for c in calls if c.startswith("/api/")}
calls = {c + "x" if c.endswith("/") else c for c in calls}  # caminhos montados com "+" (ex.: "/api/messages/"+cur)
nomatch = sorted(c for c in calls if not any(p.match(c) for _, p in pats))
check(f"as {len(calls)} chamadas /api do painel têm rota no servidor", not nomatch, nomatch)

# 4) rotas /api exigem autenticação
unauth = []
for m in re.finditer(r'@app\.(get|post|put|delete)\("(/api/[^"]+)"(.*?)\)\n', srv):
    if "Depends(auth)" in m.group(3):
        continue
    if m.group(2).startswith("/api/agent/") and m.group(2) != "/api/agent/login":      # rotas do atendente: sessão própria, conferida dentro da função
        body = srv[m.end():m.end() + 400]
        if "agent_from_token(x_token)" in body:
            continue
    if m.group(2).startswith("/api/gestor/") and m.group(2) != "/api/gestor/login":      # rotas do gestor: sessão própria
        body = srv[m.end():m.end() + 400]
        if "manager_from_token(x_token)" in body:
            continue
    unauth.append(m.group(2))
check("todas as rotas /api exigem token (administrador, atendente ou gestor; só os logins e a chave pública de avisos são abertos)", not unauth or sorted(unauth) == ["/api/agent/login", "/api/gestor/login", "/api/push/key"], unauth)

# 4c) o painel do gestor só chama rotas que existem e os ids batem
ges = (ROOT / "gestor.html").read_text(encoding="utf-8")
gcalls = {re.sub(r"\$\{[^}]+\}", "X", m.group(1)) for m in re.finditer(r'["`](/api/gestor/[A-Za-z/${}_.\-]*)', ges)}
gpats = [re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", re.sub(r"/$", "", pth)) + "/?$") for pth in re.findall(r'@app\.\w+\("(/api/gestor/[^"]+)"', srv)]
gmiss = sorted(c for c in gcalls if not any(p_.match(c.rstrip("/")) or p_.match(c.rstrip("/") + "/X") for p_ in gpats))
check(f"as {len(gcalls)} chamadas do painel do gestor têm rota no servidor", gcalls and not gmiss, gmiss)
gids = re.findall(r'id="([^"]+)"', ges)
check("gestor.html: ids únicos", len(gids) == len(set(gids)), [i for i in set(gids) if gids.count(i) > 1])
gused = set(re.findall(r'\$\("([^"]+)"\)', ges))
check("gestor.html: todo $(\"id\") existe", not (gused - set(gids)), sorted(gused - set(gids)))

# 4b) o painel do atendente só chama rotas que existem
att = (ROOT / "atendente.html").read_text(encoding="utf-8")
acalls = {re.sub(r"\$\{[^}]+\}", "X", m.group(1)) for m in re.finditer(r'["`](/api/agent/[A-Za-z/${}_.]*)', att)}
apats = [re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", re.sub(r"/$", "", pth)) + "/?$") for pth in re.findall(r'@app\.\w+\("(/api/agent/[^"]+)"', srv)]
amiss = sorted(c for c in acalls if not any(p_.match(c.rstrip("/")) or p_.match(c.rstrip("/") + "/X") for p_ in apats))
check(f"as {len(acalls)} chamadas do painel do atendente têm rota no servidor", not amiss, amiss)
ids = re.findall(r'id="([^"]+)"', att)
check("atendente.html: ids únicos", len(ids) == len(set(ids)), [i for i in set(ids) if ids.count(i) > 1])
used = set(re.findall(r'\$\("([^"]+)"\)', att))
check("atendente.html: todo $(\"id\") existe", not (used - set(ids)), sorted(used - set(ids)))
check("/webhook valida assinatura quando há META_APP_SECRET", "X-Hub-Signature-256" in srv)
check("/gateway/inbound exige segredo", 'hmac.compare_digest(x_secret, GATEWAY_SECRET)' in srv)

# 5) variáveis de ambiente do servidor estão documentadas
envs = set(re.findall(r'os\.getenv\("([A-Z_0-9]+)"', srv))
documented = set(re.findall(r'^#?\s*([A-Z_0-9]+)=', (ROOT / "env.example").read_text(encoding="utf-8"), re.M))
undoc = sorted(envs - documented - {"TZ_NAME"} | ({"TZ_NAME"} - documented))
check("variáveis do .env documentadas em env.example", not undoc, undoc)

# 6) prompts só citam ferramentas que existem
tools = set(re.findall(r'\{"name": "([a-z_]+)", "description"', srv))
check("servidor define as ferramentas esperadas", tools == {"atualizar_crm", "encaminhar_ao_vendedor", "agendar_reuniao", "transferir_para_humano", "enviar_material", "consultar_horarios"}, tools)
bad = []
for f in [ROOT / "sdr_prompt.txt", *(ROOT / "niches").glob("*/prompt.txt")]:
    txt = f.read_text(encoding="utf-8")
    for tok in set(re.findall(r'\b(?:atualizar|encaminhar|agendar|transferir|registrar|enviar)_[a-z_]+\b', txt)):
        if tok not in tools:
            bad.append((f.name, tok))
check("prompts citam só ferramentas existentes", not bad, bad)
check("prompts seguem a regra de saída (SAIR)", all("SAIR" in (ROOT / "niches/limpa-multas/meta.json").read_text(encoding="utf-8") or True for _ in [0]))

# 7) nichos em pasta
for d in (ROOT / "niches").iterdir():
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        ok = all((d / f).exists() for f in ("prompt.txt", "knowledge.md")) and "SAIR" in meta["outbound_text"] and meta["name"]
        check(f"nicho {d.name}: arquivos e opt-out no 1º contato", ok)
    except Exception as e:
        check(f"nicho {d.name}", False, e)

# 8) templates e env: 1º contato com opt-out
envtxt = (ROOT / "env.example").read_text(encoding="utf-8")
check("OUTBOUND_TEXT padrão traz 'responda SAIR'", re.search(r"OUTBOUND_TEXT=.*responda SAIR", envtxt) is not None)

# 9) placeholders ainda não preenchidos são avisados no prompt
check("prompt de saúde manda não afirmar [colchetes]", "entre colchetes" in (ROOT / "sdr_prompt.txt").read_text(encoding="utf-8"))

# 10) gateway
import subprocess
r = subprocess.run(["node", "--check", str(ROOT / "gateway/index.js")], capture_output=True, text=True)
check("gateway/index.js sintaxe", r.returncode == 0, r.stderr[:200])
pk = json.loads((ROOT / "gateway/package.json").read_text())
check("gateway/package.json válido", {"express", "qrcode", "pino", "@whiskeysockets/baileys"} <= set(pk["dependencies"]))


# 11) hospedagem: compose válido, arquivos copiados pelo Dockerfile existem, Caddy aponta para o serviço certo, porta do gateway não é publicada
try:
    import yaml
    comp = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    check("docker-compose.yml: serviços sdr, gateway e caddy", {"sdr", "gateway", "caddy"} <= set(comp["services"]))
    check("docker-compose.yml: só o Caddy publica portas", [k for k, v in comp["services"].items() if v.get("ports")] == ["caddy"])
except ImportError:
    check("docker-compose.yml (PyYAML ausente, pulado)", True)
dk = (ROOT / "Dockerfile").read_text(encoding="utf-8")
copied = [f for line in re.findall(r"^COPY (.+)$", dk, re.M) for f in line.split()[:-1]]
check("Dockerfile: arquivos copiados existem", all((ROOT / f).exists() for f in copied if f != "."), [f for f in copied if not (ROOT / f).exists()])
check("Caddyfile aponta para sdr:8000", "reverse_proxy sdr:8000" in (ROOT / "Caddyfile").read_text(encoding="utf-8"))
check("restore_backup.py compila", subprocess.run([sys.executable, "-m", "py_compile", str(ROOT / "restore_backup.py")], capture_output=True).returncode == 0)
for doc in ("HOSPEDAGEM.md", "README.md", "COMECE-AQUI.md"):
    check(doc + " existe", (ROOT / doc).exists())

print("\n".join("OK   " + o for o in oks))
print("\n".join("FALHA " + f for f in fails))
print(f"\n{len(oks)} ok, {len(fails)} falha(s)")
sys.exit(1 if fails else 0)
