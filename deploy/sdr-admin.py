#!/usr/bin/env python3
"""sdr-admin: kit do OPERADOR para hospedar uma instância isolada do SDR por cliente (Docker + Caddy), com controle de assinatura.

Cada cliente tem: pasta própria, .env próprio (chaves e senhas geradas), banco e sessão do WhatsApp em volumes próprios, domínio próprio.
Só usa a biblioteca padrão do Python. Rode no servidor (Linux com Docker). Veja deploy/GUIA-OPERADOR.md.

  python3 deploy/sdr-admin.py iniciar --dominio-base sdr.seudominio.com.br --email voce@seudominio.com.br
  python3 deploy/sdr-admin.py construir
  python3 deploy/sdr-admin.py novo acme --nome "Acme Ltda" --provider official --dias 30 --anthropic-key sk-ant-...
  python3 deploy/sdr-admin.py listar | renovar | suspender | retomar | suspender-vencidos | remover | atualizar | backup | token

Opções globais: --raiz PASTA (padrão /opt/sdr-clientes ou $SDR_HOME) e --simular (só grava arquivos; não chama o Docker; usado nos testes).
"""
import argparse, json, os, re, secrets, shutil, subprocess, sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent           # pasta sdr-whatsapp (de onde saem as imagens)
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
RESERVED = {"proxy", "admin", "www", "api", "painel", "main", "default"}
SIM = False
ROOT = Path(os.getenv("SDR_HOME", "/opt/sdr-clientes"))
CMDLOG = []                                              # comandos que seriam executados (modo --simular)


RAISE = False                                            # True quando chamado por outro programa (painel do operador): erros viram exceção


class AdminError(SystemExit):
    def __init__(self, msg, code=1):
        super().__init__(code)
        self.msg = msg


def die(msg, code=1):
    if RAISE:
        raise AdminError(msg, code)
    print("ERRO:", msg, file=sys.stderr)
    sys.exit(code)


def run(cmd, cwd=None, check=True, capture=False, stdin=None):
    """Executa um comando do Docker. Em --simular só registra."""
    CMDLOG.append(([str(c) for c in cmd], str(cwd) if cwd else None, stdin))
    if SIM:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    try:
        return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=capture or stdin is not None, input=stdin)
    except FileNotFoundError:
        die(f"programa não encontrado: {cmd[0]} (o Docker está instalado?)")
    except subprocess.CalledProcessError as e:
        die(f"falhou: {' '.join(map(str, cmd))}\n{(e.stderr or '').strip()[:500]}")


# ---------- cadastro (clientes.json) ----------
def reg_path():
    return ROOT / "clientes.json"


def load_reg():
    try:
        return json.loads(reg_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        die("Operação não iniciada nesta pasta. Rode primeiro: sdr-admin.py iniciar --dominio-base ... --email ...")
    except ValueError:
        die(f"{reg_path()} está corrompido")


def save_reg(reg):
    tmp = reg_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, reg_path())


def client_dir(slug):
    return ROOT / "clientes" / slug


def get_client(reg, slug):
    c = reg["clientes"].get(slug)
    if not c:
        die(f"cliente '{slug}' não encontrado (veja: listar)")
    return c


def compose(slug, *args, **kw):
    return run(["docker", "compose", *args], cwd=client_dir(slug), **kw)


# ---------- geração de arquivos ----------
def rand(n=24):
    return secrets.token_urlsafe(n)


def env_text(c, secrets_):
    """.env do cliente. Chaves vazias (Anthropic, Meta) são preenchidas por você ou pelo cliente depois."""
    L = ["# Gerado pelo sdr-admin. Contém chaves: não versione, não envie por e-mail.",
         f"PROVIDER={c['provider']}", f"PUBLIC_URL=https://{c['dominio']}", "TZ_NAME=America/Sao_Paulo",
         f"DASH_TOKEN={secrets_['dash']}", f"ANTHROPIC_API_KEY={secrets_.get('anthropic', '')}", f"CLAUDE_MODEL={c.get('modelo', 'claude-haiku-5-5')}",
         "BACKUP_AUTO=1", "BACKUP_KEEP=14", f"LINES_MAX={c.get('max_numeros', 1 if c['provider'] == 'official' else 3)}"]
    if c["provider"] == "qr":
        L += [f"GATEWAY_SECRET={secrets_['gateway']}", "GATEWAY_URL=http://gateway:3001"]
    else:
        L += [f"WHATSAPP_TOKEN={secrets_.get('wa_token', '')}", f"WHATSAPP_PHONE_ID={secrets_.get('wa_phone_id', '')}",
              f"META_APP_SECRET={secrets_.get('meta_secret', '')}", f"VERIFY_TOKEN={secrets_['verify']}"]
    return "\n".join(L) + "\n"


def compose_text(slug, c):
    qr = c["provider"] == "qr"
    t = [f"name: sdr-{slug}", "services:", "  sdr:", "    image: sdr-server:latest", f"    container_name: sdr-{slug}",
         "    restart: unless-stopped", "    env_file: .env", "    mem_limit: 768m"]
    if qr:
        t += ["    environment:", "      GATEWAY_URL: http://gateway:3001", "    depends_on: [gateway]"]
    t += ["    volumes:", "      - sdr-data:/data", "    networks: [default, sdrnet]"]
    if qr:
        t += ["  gateway:", "    image: sdr-gateway:latest", f"    container_name: sdr-{slug}-gateway", "    restart: unless-stopped", "    env_file: .env",
              "    mem_limit: 512m", "    environment:", "      INBOUND_URL: http://sdr:8000/gateway/inbound", '      GATEWAY_PORT: "3001"',
              "    volumes:", "      - wa-session:/session"]
    t += ["volumes:", "  sdr-data:"] + (["  wa-session:"] if qr else [])
    t += ["networks:", "  sdrnet:", "    external: true", ""]
    return "\n".join(t)


def caddy_text(reg):
    out = ["{", f"\temail {reg['email']}", "}", ""]
    if reg.get("dominio_operador"):                      # só /cobranca/* chega ao receptor de pagamentos; o painel do operador NÃO é publicado
        out += [f"{reg['dominio_operador']} {{", "\tencode gzip", "\thandle /cobranca/* {", "\t\treverse_proxy host.docker.internal:8900", "\t}",
                "\thandle {", '\t\trespond "Não encontrado" 404', "\t}", "}", ""]
    for slug, c in sorted(reg["clientes"].items()):
        out.append(f"{c['dominio']} {{")
        if c["status"] == "suspenso":
            out += ['\trespond "Acesso suspenso. Entre em contato com o suporte." 503']
        else:
            out += ["\tencode gzip", f"\treverse_proxy sdr-{slug}:8000",
                    "\theader {", '\t\tStrict-Transport-Security "max-age=31536000"', "\t\tX-Content-Type-Options nosniff", "\t\tReferrer-Policy no-referrer", "\t}"]
        out += ["}", ""]
    return "\n".join(out)


PROXY_COMPOSE = """name: sdr-proxy
services:
  caddy:
    image: caddy:2
    container_name: sdr-proxy
    restart: unless-stopped
    extra_hosts: ["host.docker.internal:host-gateway"]
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    networks: [sdrnet]
volumes:
  caddy-data:
networks:
  sdrnet:
    external: true
"""


def write_caddy(reg, reload=True):
    p = ROOT / "proxy"
    p.mkdir(parents=True, exist_ok=True)
    (p / "Caddyfile").write_text(caddy_text(reg), encoding="utf-8")
    if reload:
        run(["docker", "exec", "sdr-proxy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile"], check=False)


def write_private(path, text):
    path.write_text(text, encoding="utf-8")
    if os.name == "posix":
        os.chmod(path, 0o600)


def days_left(c):
    try:
        return (date.fromisoformat(c["valido_ate"]) - date.today()).days
    except (KeyError, ValueError):
        return None


# ---------- comandos ----------
def cmd_iniciar(a):
    ROOT.mkdir(parents=True, exist_ok=True)
    if reg_path().exists():
        die("já iniciado nesta pasta")
    if not DOMAIN_RE.match(a.dominio_base):
        die("--dominio-base inválido (ex.: sdr.seudominio.com.br)")
    if "@" not in a.email:
        die("--email inválido (o Let's Encrypt usa para avisos de certificado)")
    if a.dominio_operador and not DOMAIN_RE.match(a.dominio_operador):
        die("--dominio-operador inválido (ex.: cobranca.seudominio.com.br)")
    reg = {"dominio_base": a.dominio_base, "email": a.email, "clientes": {}, "contato": a.contato or a.email}
    if a.dominio_operador:
        reg["dominio_operador"] = a.dominio_operador.lower()
    save_reg(reg)
    (ROOT / "clientes").mkdir(exist_ok=True)
    (ROOT / "proxy").mkdir(exist_ok=True)
    (ROOT / "proxy" / "docker-compose.yml").write_text(PROXY_COMPOSE, encoding="utf-8")
    write_caddy(reg, reload=False)
    run(["docker", "network", "create", "sdrnet"], check=False)
    run(["docker", "compose", "up", "-d"], cwd=ROOT / "proxy")
    print(f"Pronto. Cada cliente ganha o endereço <nome>.{a.dominio_base} (crie um registro DNS curinga *.{a.dominio_base} apontando para este servidor).")
    print("Próximo passo: construir (cria as imagens) e depois novo <cliente>.")


def cmd_construir(a):
    run(["docker", "build", "-t", "sdr-server:latest", str(PROJ)])
    run(["docker", "build", "-t", "sdr-gateway:latest", str(PROJ / "gateway")])
    print("Imagens prontas: sdr-server e sdr-gateway.")


def cmd_novo(a):
    reg = load_reg()
    slug = a.slug
    if not SLUG_RE.match(slug) or slug in RESERVED:
        die("nome do cliente inválido: use letras minúsculas, números e hífen (começando por letra), 2 a 31 caracteres")
    if slug in reg["clientes"] or client_dir(slug).exists():
        die(f"o cliente '{slug}' já existe")
    dominio = (a.dominio or f"{slug}.{reg['dominio_base']}").lower()
    if not DOMAIN_RE.match(dominio):
        die("domínio inválido")
    if any(c["dominio"] == dominio for c in reg["clientes"].values()):
        die("este domínio já está em uso por outro cliente")
    if a.provider == "qr" and not a.aceito_risco_qr:
        die("o modo QR usa uma biblioteca não oficial e pode violar os Termos do WhatsApp (risco de banimento do número do cliente).\n"
            "Confirme que o cliente foi informado e aceitou por escrito, e repita com --aceito-risco-qr (a data fica registrada).")
    if a.dias is not None and a.ate:
        die("use --dias ou --ate, não os dois")
    if not (0 <= a.tolerancia <= 30) or not (1 <= a.periodo_dias <= 400):
        die("--tolerancia deve ficar entre 0 e 30 dias e --periodo-dias entre 1 e 400")
    valido = a.ate or (date.today() + timedelta(days=a.dias if a.dias is not None else 30)).isoformat()
    try:
        date.fromisoformat(valido)
    except ValueError:
        die("--ate deve ser AAAA-MM-DD")
    c = {"nome": a.nome or slug, "dominio": dominio, "provider": a.provider, "status": "ativo", "criado": date.today().isoformat(),
         "valido_ate": valido, "observacao": a.obs or "", "tolerancia_dias": a.tolerancia, "periodo_dias": a.periodo_dias, "cobranca": {}}
    if a.provider == "qr":
        c["risco_qr_aceito_em"] = datetime.now().isoformat(timespec="seconds")
    sec = {"dash": rand(18), "gateway": rand(24), "verify": rand(16), "anthropic": a.anthropic_key or "", "wa_token": a.wa_token or "",
           "wa_phone_id": a.wa_phone_id or "", "meta_secret": a.meta_secret or ""}
    d = client_dir(slug)
    d.mkdir(parents=True)
    write_private(d / ".env", env_text(c, sec))
    (d / "docker-compose.yml").write_text(compose_text(slug, c), encoding="utf-8")
    reg["clientes"][slug] = c
    save_reg(reg)
    write_caddy(reg)
    compose(slug, "up", "-d")
    print(f"Cliente '{slug}' criado ({a.provider}), válido até {valido}.")
    print(f"  Painel:     https://{dominio}")
    print(f"  DASH_TOKEN: {sec['dash']}   (senha do painel; guarde e entregue ao cliente por canal seguro)")
    if a.provider == "official":
        print(f"  Webhook da Meta: https://{dominio}/webhook   Verify token: {sec['verify']}")
        falta = [k for k, v in (("WHATSAPP_TOKEN", a.wa_token), ("WHATSAPP_PHONE_ID", a.wa_phone_id), ("META_APP_SECRET", a.meta_secret)) if not v]
        if falta:
            print(f"  Falta: {', '.join(falta)} em {d}/.env (depois: sdr-admin.py reiniciar {slug})")
    else:
        print("  No painel > Envio e conexão, o cliente escaneia o QR com o WhatsApp dele.")
    if not a.anthropic_key:
        print(f"  Falta: ANTHROPIC_API_KEY em {d}/.env (a chave do cliente, ou a sua se você fornece o Claude) e depois: sdr-admin.py reiniciar {slug}")


def cmd_listar(a):
    reg = load_reg()
    if not reg["clientes"]:
        print("Nenhum cliente ainda.")
        return
    print(f"{'cliente':<18}{'domínio':<34}{'modo':<10}{'estado':<10}{'válido até':<12}dias")
    for slug, c in sorted(reg["clientes"].items()):
        dl = days_left(c)
        flag = "  VENCIDO" if dl is not None and dl < 0 and c["status"] == "ativo" else ""
        print(f"{slug:<18}{c['dominio']:<34}{c['provider']:<10}{c['status']:<10}{c.get('valido_ate', '-'):<12}{dl if dl is not None else '-'}{flag}")


def _set_status(slug, status):
    reg = load_reg()
    c = get_client(reg, slug)
    c["status"] = status
    save_reg(reg)
    write_caddy(reg)
    compose(slug, "stop" if status == "suspenso" else "start", check=False)


def cmd_suspender(a):
    _set_status(a.slug, "suspenso")
    print(f"'{a.slug}' suspenso: o sistema parou e o endereço mostra aviso de acesso suspenso. Os dados continuam guardados.")


def cmd_retomar(a):
    reg = load_reg()
    c = get_client(reg, a.slug)
    dl = days_left(c)
    if dl is not None and dl < 0 and not a.mesmo_vencido:
        die("a assinatura está vencida. Use 'renovar' (que já reativa) ou --mesmo-vencido.")
    _set_status(a.slug, "ativo")
    set_notice(a.slug, None)
    print(f"'{a.slug}' reativado.")


def renovar_cliente(slug, dias=None, ate=None):
    """Renova a assinatura: soma ao prazo que sobrou (ou parte de hoje se já venceu), reativa se estiver suspenso e limpa o aviso. Devolve a nova data."""
    reg = load_reg()
    c = get_client(reg, slug)
    if ate:
        try:
            novo = date.fromisoformat(ate)
        except ValueError:
            die("--ate deve ser AAAA-MM-DD")
    else:
        base = max(date.today(), date.fromisoformat(c["valido_ate"])) if c.get("valido_ate") else date.today()
        novo = base + timedelta(days=dias or c.get("periodo_dias", 30))
    c["valido_ate"] = novo.isoformat()
    reativou = c["status"] == "suspenso"
    save_reg(reg)
    if reativou:
        _set_status(slug, "ativo")
    set_notice(slug, None)
    return novo, reativou


def cmd_renovar(a):
    novo, reativou = renovar_cliente(a.slug, dias=None if a.ate else a.dias, ate=a.ate)
    print(f"'{a.slug}' válido até {novo.isoformat()}.")
    if reativou:
        print("Reativado.")


# ---------- aviso gradual no painel do cliente ----------
def notice_for(c, avisar=5, contato=""):
    """Texto do aviso que o cliente vê no topo do painel, conforme a situação da assinatura."""
    dl = days_left(c)
    contato = c.get("contato") or contato
    fale = f" Para renovar, fale com {contato}." if contato else " Para renovar, entre em contato com o suporte."
    tol = c.get("tolerancia_dias", 3)
    if dl is None or dl > avisar:
        return None
    if dl > 2:
        return {"level": "info", "text": f"Sua assinatura vence em {dl} dias ({c['valido_ate']}).{fale}"}
    if dl >= 0:
        return {"level": "warn", "text": "Sua assinatura vence hoje." + fale if dl == 0 else f"Sua assinatura vence em {dl} dia(s) ({c['valido_ate']}).{fale}"}
    restam = tol + dl
    if restam >= 0:
        return {"level": "error", "text": f"Assinatura vencida há {-dl} dia(s). O acesso será suspenso em {restam} dia(s) se o pagamento não for confirmado.{fale}"}
    return None


def set_notice(slug, notice):
    """Grava (ou apaga) o aviso dentro do contêiner do cliente. Falha em silêncio se o cliente estiver parado."""
    if notice:
        run(["docker", "exec", "-i", f"sdr-{slug}", "sh", "-c", "cat > /data/aviso-operador.json"], check=False, stdin=json.dumps(notice, ensure_ascii=False))
    else:
        run(["docker", "exec", f"sdr-{slug}", "rm", "-f", "/data/aviso-operador.json"], check=False)


def sync_notices(reg, avisar=5):
    """Atualiza o aviso de cada cliente ativo (só chama o Docker quando o texto muda)."""
    mudou = []
    for slug, c in sorted(reg["clientes"].items()):
        if c["status"] != "ativo":
            continue
        n = notice_for(c, avisar, reg.get("contato", ""))
        sig = json.dumps(n, ensure_ascii=False, sort_keys=True) if n else ""
        if sig != c.get("aviso_sig", ""):
            set_notice(slug, n)
            c["aviso_sig"] = sig
            mudou.append(slug)
    if mudou:
        save_reg(reg)
    return mudou


def rotina_vencimentos(tolerancia=None, avisar=5):
    """Suspende quem passou da tolerância e atualiza os avisos. Devolve (suspensos, vencem_em_breve)."""
    reg = load_reg()
    suspensos = []
    for slug, c in sorted(reg["clientes"].items()):
        dl = days_left(c)
        tol = c.get("tolerancia_dias", 3) if tolerancia is None else tolerancia
        if c["status"] == "ativo" and dl is not None and dl < -tol:
            _set_status(slug, "suspenso")
            suspensos.append(slug)
    reg = load_reg()
    sync_notices(reg, avisar)
    em_breve = [f"{s} ({days_left(c)} dia(s))" for s, c in sorted(reg["clientes"].items()) if c["status"] == "ativo" and days_left(c) is not None and 0 <= days_left(c) <= avisar]
    return suspensos, em_breve


def cmd_suspender_vencidos(a):
    suspensos, em_breve = rotina_vencimentos(a.tolerancia, a.avisar)
    print("Suspensos por vencimento:", ", ".join(suspensos) if suspensos else "nenhum")
    if em_breve:
        print(f"Vencem em até {a.avisar} dia(s):", ", ".join(em_breve))


def cmd_vincular(a):
    """Liga o cliente do provedor de pagamento (ex.: cus_123 no Asaas) ao cliente do sistema, para a renovação automática."""
    reg = load_reg()
    c = get_client(reg, a.slug)
    for outro, o in reg["clientes"].items():
        if outro != a.slug and o.get("cobranca", {}).get(a.provedor) == a.cliente_id:
            die(f"este identificador já está ligado ao cliente '{outro}'")
    c.setdefault("cobranca", {})[a.provedor] = a.cliente_id
    save_reg(reg)
    print(f"'{a.slug}' ligado ao cliente {a.cliente_id} do {a.provedor}. Pagamentos dele renovam a assinatura sozinhos.")


def cmd_remover(a):
    if not a.confirmo_apagar_dados:
        die("isto APAGA o banco, os arquivos e a sessão do WhatsApp do cliente, sem volta. Faça backup antes e repita com --confirmo-apagar-dados")
    reg = load_reg()
    get_client(reg, a.slug)
    compose(a.slug, "down", "-v", check=False)
    shutil.rmtree(client_dir(a.slug), ignore_errors=True)
    del reg["clientes"][a.slug]
    save_reg(reg)
    write_caddy(reg)
    print(f"'{a.slug}' removido.")


def cmd_reiniciar(a):
    reg = load_reg()
    get_client(reg, a.slug)
    compose(a.slug, "up", "-d", "--force-recreate")
    print(f"'{a.slug}' reiniciado (relê o .env).")


def cmd_atualizar(a):
    reg = load_reg()
    cmd_construir(a)
    for slug, c in sorted(reg["clientes"].items()):
        if c["status"] == "ativo":
            compose(slug, "up", "-d")
            print(f"atualizado: {slug}")
    print("Os volumes (dados e sessões) foram mantidos. Faça backup antes de atualizar em produção.")


def cmd_backup(a):
    reg = load_reg()
    if not a.todos and not a.slug:
        die("informe o cliente ou --todos")
    slugs = sorted(reg["clientes"]) if a.todos else [a.slug]
    dest = Path(a.destino)
    for slug in slugs:
        get_client(reg, slug)
        out = dest / slug
        out.mkdir(parents=True, exist_ok=True)
        run(["docker", "cp", f"sdr-{slug}:/data/backups/.", str(out)], check=False)
        print(f"backups de '{slug}' copiados para {out} (contêm dados pessoais de leads: proteja o acesso)")


def cmd_token(a):
    reg = load_reg()
    get_client(reg, a.slug)
    m = re.search(r"^DASH_TOKEN=(.*)$", (client_dir(a.slug) / ".env").read_text(encoding="utf-8"), re.M)
    print(m.group(1) if m else "(sem DASH_TOKEN)")


def build_parser():
    p = argparse.ArgumentParser(prog="sdr-admin", description=__doc__.split("\n")[0])
    p.add_argument("--raiz", help="pasta de dados do operador (padrão /opt/sdr-clientes ou $SDR_HOME)")
    p.add_argument("--simular", action="store_true", help="só grava arquivos; não chama o Docker")
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("iniciar"); x.add_argument("--dominio-base", required=True); x.add_argument("--email", required=True)
    x.add_argument("--dominio-operador", help="endereço público do receptor de pagamentos (ex.: cobranca.seudominio.com.br)"); x.add_argument("--contato", help="como o cliente fala com você (aparece nos avisos de vencimento)"); x.set_defaults(f=cmd_iniciar)
    x = s.add_parser("construir"); x.set_defaults(f=cmd_construir)
    x = s.add_parser("novo"); x.add_argument("slug"); x.add_argument("--nome"); x.add_argument("--provider", choices=["qr", "official"], required=True)
    x.add_argument("--dominio"); x.add_argument("--dias", type=int); x.add_argument("--ate"); x.add_argument("--anthropic-key")
    x.add_argument("--wa-token"); x.add_argument("--wa-phone-id"); x.add_argument("--meta-secret"); x.add_argument("--obs")
    x.add_argument("--aceito-risco-qr", action="store_true"); x.add_argument("--tolerancia", type=int, default=3, help="dias após o vencimento antes de suspender")
    x.add_argument("--periodo-dias", type=int, default=30, help="dias somados a cada pagamento confirmado"); x.set_defaults(f=cmd_novo)
    x = s.add_parser("listar"); x.set_defaults(f=cmd_listar)
    x = s.add_parser("suspender"); x.add_argument("slug"); x.set_defaults(f=cmd_suspender)
    x = s.add_parser("retomar"); x.add_argument("slug"); x.add_argument("--mesmo-vencido", action="store_true"); x.set_defaults(f=cmd_retomar)
    x = s.add_parser("renovar"); x.add_argument("slug"); g = x.add_mutually_exclusive_group(); g.add_argument("--dias", type=int, help="padrão: o período do cliente (30)"); g.add_argument("--ate"); x.set_defaults(f=cmd_renovar)
    x = s.add_parser("suspender-vencidos"); x.add_argument("--tolerancia", type=int, default=None, help="dias de tolerância após o vencimento (padrão: o de cada cliente)"); x.add_argument("--avisar", type=int, default=5)
    x.set_defaults(f=cmd_suspender_vencidos)
    x = s.add_parser("vincular"); x.add_argument("slug"); x.add_argument("--provedor", choices=["asaas", "stripe"], required=True); x.add_argument("--cliente-id", required=True); x.set_defaults(f=cmd_vincular)
    x = s.add_parser("remover"); x.add_argument("slug"); x.add_argument("--confirmo-apagar-dados", action="store_true"); x.set_defaults(f=cmd_remover)
    x = s.add_parser("reiniciar"); x.add_argument("slug"); x.set_defaults(f=cmd_reiniciar)
    x = s.add_parser("atualizar"); x.set_defaults(f=cmd_atualizar)
    x = s.add_parser("backup"); x.add_argument("slug", nargs="?"); x.add_argument("--todos", action="store_true"); x.add_argument("--destino", required=True); x.set_defaults(f=cmd_backup)
    x = s.add_parser("token"); x.add_argument("slug"); x.set_defaults(f=cmd_token)
    return p


def main(argv=None):
    global ROOT, SIM
    a = build_parser().parse_args(argv)
    if a.raiz:
        ROOT = Path(a.raiz)
    SIM = a.simular
    a.f(a)


if __name__ == "__main__":
    main()
