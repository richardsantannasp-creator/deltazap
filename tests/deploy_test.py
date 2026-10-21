"""Testa o kit do operador (deploy/sdr-admin.py) em modo --simular: arquivos gerados, cadastro, assinatura (vencimento/suspensão) e comandos do Docker que seriam chamados."""
import contextlib, importlib.util, io, os, sys, tempfile, stat
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sdr_admin", ROOT / "deploy" / "sdr-admin.py")
A = importlib.util.module_from_spec(spec); spec.loader.exec_module(A)

OK = FAIL = 0
def check(nome, cond, extra=""):
    global OK, FAIL
    cond = bool(cond); OK += cond; FAIL += (not cond)
    print(("OK    " if cond else "FALHA ") + nome + ("" if cond else f"  -> {extra}"))

tmp = Path(tempfile.mkdtemp(prefix="sdr-op-"))
def adm(*args):
    """Roda o sdr-admin; devolve (saída, código de erro ou 0)."""
    A.CMDLOG.clear(); buf, err = io.StringIO(), io.StringIO(); code = 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        try: A.main(["--raiz", str(tmp), "--simular", *args])
        except SystemExit as e: code = e.code or 0
    return buf.getvalue() + err.getvalue(), code
def reg(): return A.json.loads((tmp / "clientes.json").read_text(encoding="utf-8"))
def env(slug): return (tmp / "clientes" / slug / ".env").read_text(encoding="utf-8")
def dc(slug): return (tmp / "clientes" / slug / "docker-compose.yml").read_text(encoding="utf-8")
def caddy(): return (tmp / "proxy" / "Caddyfile").read_text(encoding="utf-8")
def cmds(): return [" ".join(c[0]) for c in A.CMDLOG]

# ---------- iniciar ----------
out, code = adm("listar")
check("antes de iniciar, os comandos pedem 'iniciar'", code != 0 and "iniciar" in out)
out, code = adm("iniciar", "--dominio-base", "x", "--email", "a@b.com")
check("iniciar recusa domínio inválido", code != 0)
out, code = adm("iniciar", "--dominio-base", "sdr.exemplo.com.br", "--email", "ops@exemplo.com.br")
check("iniciar cria cadastro, proxy e rede", code == 0 and (tmp / "proxy" / "docker-compose.yml").exists() and "email ops@exemplo.com.br" in caddy() and any("network create sdrnet" in c for c in cmds()), out)
check("iniciar duas vezes é recusado", adm("iniciar", "--dominio-base", "sdr.exemplo.com.br", "--email", "ops@exemplo.com.br")[1] != 0)

# ---------- novo (API oficial) ----------
out, code = adm("novo", "acme", "--nome", "Acme Ltda", "--provider", "official", "--dias", "30", "--anthropic-key", "sk-ant-teste", "--wa-token", "EAAG", "--wa-phone-id", "123")
e = env("acme")
check("cliente oficial: .env com as chaves e sem campos do gateway", code == 0 and "PROVIDER=official" in e and "ANTHROPIC_API_KEY=sk-ant-teste" in e and "WHATSAPP_TOKEN=EAAG" in e and "GATEWAY_SECRET" not in e, e)
check("verify token e senha do painel são aleatórios (não o padrão)", "troque-este-token" not in e and len([l for l in e.splitlines() if l.startswith("VERIFY_TOKEN=")][0]) > 20 and len([l for l in e.splitlines() if l.startswith("DASH_TOKEN=")][0]) > 20)
check(".env só pode ser lido pelo dono (chmod 600)", os.name != "posix" or stat.S_IMODE((tmp / "clientes" / "acme" / ".env").stat().st_mode) == 0o600)
check("sem gateway no compose e com rede do proxy", "gateway:" not in dc("acme").replace("INBOUND", "") and "sdrnet" in dc("acme") and "container_name: sdr-acme" in dc("acme") and "wa-session" not in dc("acme"), dc("acme"))
check("domínio padrão, proxy reverso e validade de 30 dias", "acme.sdr.exemplo.com.br {" in caddy() and "reverse_proxy sdr-acme:8000" in caddy() and reg()["clientes"]["acme"]["valido_ate"] == (date.today() + timedelta(days=30)).isoformat())
check("mostra webhook da Meta e o que falta", "https://acme.sdr.exemplo.com.br/webhook" in out and "META_APP_SECRET" in out, out)
check("sobe o cliente e recarrega o proxy", any(c.endswith("compose up -d") for c in cmds()) and any("caddy reload" in c for c in cmds()), cmds())
try:
    import yaml
    d = yaml.safe_load(dc("acme")); check("docker-compose gerado é YAML válido", d["services"]["sdr"]["image"] == "sdr-server:latest" and d["networks"]["sdrnet"]["external"] is True)
except ImportError:
    check("docker-compose gerado tem as chaves esperadas", "services:" in dc("acme") and "volumes:" in dc("acme"))

# ---------- novo (QR) ----------
out, code = adm("novo", "beta", "--provider", "qr")
check("modo QR exige aceite explícito do risco", code != 0 and "Termos do WhatsApp" in out and not (tmp / "clientes" / "beta").exists(), out)
out, code = adm("novo", "beta", "--provider", "qr", "--aceito-risco-qr", "--dias", "7")
check("modo QR com aceite: gateway, volume da sessão, segredo e data do aceite registrada",
      code == 0 and "gateway:" in dc("beta") and "wa-session:/session" in dc("beta") and "GATEWAY_SECRET=" in env("beta") and reg()["clientes"]["beta"].get("risco_qr_aceito_em"), out)
check("o aviso sobre a chave do Claude aparece quando falta", "ANTHROPIC_API_KEY" in out)
check("cada cliente tem senhas diferentes", [l for l in env("acme").splitlines() if l.startswith("DASH_TOKEN=")] != [l for l in env("beta").splitlines() if l.startswith("DASH_TOKEN=")])

# ---------- validações ----------
check("nome duplicado recusado", adm("novo", "acme", "--provider", "official")[1] != 0)
check("nome inválido e reservado recusados", adm("novo", "Acme!", "--provider", "official")[1] != 0 and adm("novo", "admin", "--provider", "official")[1] != 0 and adm("novo", "1abc", "--provider", "official")[1] != 0)
check("domínio repetido recusado", adm("novo", "gama", "--provider", "official", "--dominio", "acme.sdr.exemplo.com.br")[1] != 0)
check("--dias e --ate juntos recusados", adm("novo", "gama", "--provider", "official", "--dias", "5", "--ate", "2030-01-01")[1] != 0)
check("data inválida recusada", adm("novo", "gama", "--provider", "official", "--ate", "31/12/2030")[1] != 0)
check("validação não deixou lixo", not (tmp / "clientes" / "gama").exists() and "gama" not in reg()["clientes"])

# ---------- assinatura ----------
out, _ = adm("suspender", "acme")
check("suspender para o cliente e o endereço mostra aviso 503", reg()["clientes"]["acme"]["status"] == "suspenso" and "503" in caddy() and any(c.endswith("compose stop") for c in cmds()), cmds())
check("cliente suspenso não aparece no proxy reverso", "reverse_proxy sdr-acme" not in caddy() and "reverse_proxy sdr-beta:8000" in caddy())
c = reg(); c["clientes"]["acme"]["valido_ate"] = (date.today() - timedelta(days=2)).isoformat(); A.save_reg(c)
out, code = adm("retomar", "acme")
check("retomar um cliente vencido é recusado", code != 0 and reg()["clientes"]["acme"]["status"] == "suspenso", out)
out, _ = adm("renovar", "acme", "--dias", "30")
check("renovar parte de hoje se já venceu, e reativa", reg()["clientes"]["acme"]["valido_ate"] == (date.today() + timedelta(days=30)).isoformat() and reg()["clientes"]["acme"]["status"] == "ativo" and "Reativado" in out, out)
adm("renovar", "acme", "--dias", "30")
check("renovar antes do vencimento soma ao prazo restante", reg()["clientes"]["acme"]["valido_ate"] == (date.today() + timedelta(days=60)).isoformat())
adm("renovar", "acme", "--ate", "2031-05-01")
check("renovar com data exata", reg()["clientes"]["acme"]["valido_ate"] == "2031-05-01")
c = reg(); c["clientes"]["acme"]["valido_ate"] = (date.today() - timedelta(days=5)).isoformat(); c["clientes"]["beta"]["valido_ate"] = (date.today() - timedelta(days=2)).isoformat(); A.save_reg(c)
out, _ = adm("suspender-vencidos", "--tolerancia", "3")
check("vencidos além da tolerância são suspensos; dentro dela, não", reg()["clientes"]["acme"]["status"] == "suspenso" and reg()["clientes"]["beta"]["status"] == "ativo" and "acme" in out, out)
c = reg(); c["clientes"]["beta"]["valido_ate"] = (date.today() + timedelta(days=3)).isoformat(); A.save_reg(c)
out, _ = adm("suspender-vencidos")
check("avisa quem vence nos próximos dias", "beta" in out.split("Vencem")[-1] and "Vencem em até 5" in out, out)
out, _ = adm("listar")
check("listar mostra estado e dias restantes", "acme" in out and "suspenso" in out and "beta" in out and "qr" in out, out)
c = reg(); c["clientes"]["beta"]["valido_ate"] = (date.today() - timedelta(days=1)).isoformat(); A.save_reg(c)
check("listar sinaliza vencido ainda ativo", "VENCIDO" in adm("listar")[0])

# ---------- demais comandos ----------
tok = adm("token", "beta")[0].strip()
check("token devolve a senha do painel do cliente", tok and f"DASH_TOKEN={tok}" in env("beta"))
adm("reiniciar", "beta")
check("reiniciar recria os contêineres para reler o .env", any("force-recreate" in c for c in cmds()))
adm("atualizar")
check("atualizar reconstrói as imagens e só atualiza clientes ativos", any("docker build -t sdr-server:latest" in c for c in cmds()) and any("docker build -t sdr-gateway:latest" in c for c in cmds()) and sum(c.endswith("compose up -d") for c in cmds()) == 1, cmds())
adm("backup", "--todos", "--destino", str(tmp / "bk"))
check("backup copia do contêiner de cada cliente", sum(c.startswith("docker cp sdr-") for c in cmds()) == 2 and (tmp / "bk" / "acme").is_dir(), cmds())
check("backup sem cliente nem --todos é recusado", adm("backup", "--destino", str(tmp / "bk"))[1] != 0)
check("remover exige confirmação explícita e não apaga nada sem ela", adm("remover", "beta")[1] != 0 and (tmp / "clientes" / "beta").exists())
adm("remover", "beta", "--confirmo-apagar-dados")
check("remover apaga pasta, cadastro e rota do proxy e derruba os volumes", not (tmp / "clientes" / "beta").exists() and "beta" not in reg()["clientes"] and "sdr-beta" not in caddy() and any("compose down -v" in c for c in cmds()), cmds())
check("comando em cliente inexistente dá erro claro", adm("suspender", "zzz")[1] != 0)

print(f"\n{OK} ok, {FAIL} falha(s)")
sys.exit(1 if FAIL else 0)
