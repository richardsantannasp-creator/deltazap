"""Testa cobrança: avisos graduais, tolerância, receptor de pagamentos (Asaas/Stripe/genérico), idempotência e painel do operador (modo simulado)."""
import contextlib, hashlib, hmac, http.client, importlib.util, io, json, os, sys, tempfile, threading, time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.update(OPERADOR_TOKEN="token-do-operador-123456", ASAAS_WEBHOOK_TOKEN="asaas-tok-xyz", STRIPE_WEBHOOK_SECRET="whsec_teste", PAY_HMAC_SECRET="seg-generico")
spec = importlib.util.spec_from_file_location("sdr_cobranca", ROOT / "deploy" / "sdr-cobranca.py")
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
A = C.A

OK = FAIL = 0
def check(nome, cond, extra=""):
    global OK, FAIL
    cond = bool(cond); OK += cond; FAIL += (not cond)
    print(("OK    " if cond else "FALHA ") + nome + ("" if cond else f"  -> {extra}"))

tmp = Path(tempfile.mkdtemp(prefix="sdr-bill-"))
def adm(*args):
    A.CMDLOG.clear(); buf = io.StringIO(); code = 0; A.RAISE = False
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try: A.main(["--raiz", str(tmp), "--simular", *args])
        except SystemExit as e: code = e.code or 0
    A.RAISE = True
    return buf.getvalue(), code
def reg(): return json.loads((tmp / "clientes.json").read_text(encoding="utf-8"))
def setdate(slug, delta):
    r = reg(); r["clientes"][slug]["valido_ate"] = (date.today() + timedelta(days=delta)).isoformat(); (tmp / "clientes.json").write_text(json.dumps(r))
def notices(): return [c for c in A.CMDLOG if "docker" == c[0][0] and "exec" in c[0] and "-i" in c[0]]

adm("iniciar", "--dominio-base", "ex.com.br", "--email", "a@ex.com.br", "--dominio-operador", "cobranca.ex.com.br", "--contato", "WhatsApp 11 99999-0000")
o, c = adm("novo", "acme", "--provider", "official", "--dias", "30", "--tolerancia", "2", "--periodo-dias", "30", "--wa-token", "t", "--wa-phone-id", "1", "--meta-secret", "s", "--anthropic-key", "k")
check("cliente criado com tolerância 2", c == 0 and reg()["clientes"]["acme"]["tolerancia_dias"] == 2, o)
adm("novo", "beta", "--provider", "official", "--dias", "30", "--wa-token", "t", "--wa-phone-id", "1", "--meta-secret", "s", "--anthropic-key", "k")
adm("vincular", "acme", "--provedor", "asaas", "--cliente-id", "cus_111")
adm("vincular", "beta", "--provedor", "stripe", "--cliente-id", "cus_stripe_9")
o, c = adm("vincular", "beta", "--provedor", "asaas", "--cliente-id", "cus_111")
check("identificador duplicado é recusado", c != 0 and "já está ligado" in o, o)
check("caddy: rota do operador só /cobranca/*", "handle /cobranca/*" in (tmp / "proxy" / "Caddyfile").read_text() and "host.docker.internal:8900" in (tmp / "proxy" / "Caddyfile").read_text())
check("proxy com host-gateway", "host.docker.internal:host-gateway" in (tmp / "proxy" / "docker-compose.yml").read_text())

# ---------- avisos graduais ----------
c0 = reg()["clientes"]["acme"]
def nf(delta, tol=2):
    c = dict(c0); c["valido_ate"] = (date.today() + timedelta(days=delta)).isoformat(); c["tolerancia_dias"] = tol; return A.notice_for(c, 5, reg().get("contato", ""))
check("sem aviso com 10 dias", nf(10) is None)
check("info com 5 dias", nf(5)["level"] == "info" and "5 dias" in nf(5)["text"] and "WhatsApp 11 99999-0000" in nf(5)["text"])
check("warn com 1 dia", nf(1)["level"] == "warn")
check("warn no dia", nf(0)["level"] == "warn" and "hoje" in nf(0)["text"])
check("erro vencido dentro da tolerância, com dias restantes", nf(-1)["level"] == "error" and "1 dia(s)" in nf(-1)["text"] and "suspenso" in nf(-1)["text"], nf(-1))
check("sem aviso após a tolerância (já suspenso)", nf(-3) is None)

# ---------- rotina: avisos + suspensão pela tolerância de cada cliente ----------
setdate("acme", 4); setdate("beta", 20)
o, c = adm("suspender-vencidos")
check("aviso gravado no contêiner de quem vence em 4 dias", any("sdr-acme" in " ".join(x[0]) and x[2] and "vence em 4" in x[2] for x in notices()), A.CMDLOG)
check("quem tem 20 dias não recebe aviso", not any("sdr-beta" in " ".join(x[0]) for x in notices()))
adm("suspender-vencidos")
check("repetir a rotina não reenvia o mesmo aviso", not notices())
setdate("acme", -2)
adm("suspender-vencidos")
check("vencido há 2 dias (tolerância 2) ainda ativo, com aviso de erro", reg()["clientes"]["acme"]["status"] == "ativo" and any(x[2] and "suspenso em 0 dia" in x[2] for x in notices()), A.CMDLOG)
setdate("acme", -3)
o, _ = adm("suspender-vencidos")
check("vencido há 3 dias é suspenso", reg()["clientes"]["acme"]["status"] == "suspenso" and "acme" in o)
check("tolerância própria: beta com 20 dias segue ativo", reg()["clientes"]["beta"]["status"] == "ativo")
o, _ = adm("renovar", "acme")
c = reg()["clientes"]["acme"]
check("renovar reativa, soma o período do cliente a partir de hoje e limpa o aviso", c["status"] == "ativo" and c["valido_ate"] == (date.today() + timedelta(days=30)).isoformat()
      and any("rm" in x[0] and "aviso-operador.json" in " ".join(x[0]) for x in A.CMDLOG), (c, A.CMDLOG))

# ---------- receptor ----------
A.ROOT = tmp; A.SIM = True; C.cfg_from_env()
srv = C.make_server("127.0.0.1", 0); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
def req(method, path, body=None, headers=None):
    cn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    raw = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    cn.request(method, path, raw, headers or {})
    r = cn.getresponse(); d = r.read().decode(); cn.close()
    try: j = json.loads(d)
    except ValueError: j = d
    return r.status, j
def valido(slug): return reg()["clientes"][slug]["valido_ate"]

setdate("acme", -1)
ev = {"id": "evt_1", "event": "PAYMENT_RECEIVED", "payment": {"id": "pay_1", "customer": "cus_111"}}
st, _ = req("POST", "/cobranca/asaas", ev, {"asaas-access-token": "errado"})
check("Asaas com token errado -> 401, nada muda", st == 401 and valido("acme") == (date.today() - timedelta(days=1)).isoformat())
st, j = req("POST", "/cobranca/asaas", ev, {"asaas-access-token": "asaas-tok-xyz"})
check("Asaas pagamento renova (vencido: parte de hoje)", st == 200 and valido("acme") == (date.today() + timedelta(days=30)).isoformat(), (st, j))
v1 = valido("acme")
st, j = req("POST", "/cobranca/asaas", ev, {"asaas-access-token": "asaas-tok-xyz"})
check("mesmo evento de novo é ignorado (idempotência)", st == 200 and "duplicado" in j["msg"] and valido("acme") == v1, j)
st, j = req("POST", "/cobranca/asaas", {"id": "evt_2", "event": "PAYMENT_CREATED", "payment": {"id": "p2", "customer": "cus_111"}}, {"asaas-access-token": "asaas-tok-xyz"})
check("cobrança criada (não paga) não renova", st == 200 and valido("acme") == v1)
st, j = req("POST", "/cobranca/asaas", {"id": "evt_3", "event": "PAYMENT_CONFIRMED", "payment": {"id": "p3", "customer": "cus_desconhecido"}}, {"asaas-access-token": "asaas-tok-xyz"})
check("cliente sem vínculo -> 202 e fica no histórico", st == 202 and any(e["tipo"] == "sem_vinculo" for e in C.recent_log()), (st, j))

body = json.dumps({"id": "evt_s1", "type": "invoice.paid", "data": {"object": {"customer": "cus_stripe_9"}}}).encode()
t = str(int(time.time())); sig = hmac.new(b"whsec_teste", t.encode() + b"." + body, hashlib.sha256).hexdigest()
setdate("beta", 3)
st, j = req("POST", "/cobranca/stripe", body, {"Stripe-Signature": f"t={t},v1={sig}"})
check("Stripe assinado renova (soma ao prazo que sobrava)", st == 200 and valido("beta") == (date.today() + timedelta(days=33)).isoformat(), (st, j, valido("beta")))
old = str(int(time.time()) - 4000); sig2 = hmac.new(b"whsec_teste", old.encode() + b"." + body, hashlib.sha256).hexdigest()
st, _ = req("POST", "/cobranca/stripe", body.replace(b"evt_s1", b"evt_s2"), {"Stripe-Signature": f"t={old},v1={sig2}"})
check("Stripe com data antiga (replay) -> 401", st == 401)
st, _ = req("POST", "/cobranca/stripe", body.replace(b"evt_s1", b"evt_s3"), {"Stripe-Signature": f"t={t},v1={sig}"})
check("Stripe com corpo adulterado -> 401", st == 401)

g = json.dumps({"id": "g1", "cliente": "acme", "dias": 10}).encode(); gs = hmac.new(b"seg-generico", g, hashlib.sha256).hexdigest()
v0 = valido("acme")
st, j = req("POST", "/cobranca/generico", g, {"X-Signature": gs})
check("genérico HMAC renova pelos dias informados", st == 200 and valido("acme") == (date.fromisoformat(v0) + timedelta(days=10)).isoformat(), (st, j))
st, _ = req("POST", "/cobranca/generico", g, {"X-Signature": "00"})
check("genérico com assinatura errada -> 401", st == 401)
st, _ = req("POST", "/cobranca/outro", {}, {})
check("provedor desconhecido -> 404", st == 404)

# suspenso é reativado pelo pagamento
adm("suspender", "beta"); setdate("beta", -10)
b2 = json.dumps({"id": "evt_s9", "type": "invoice.payment_succeeded", "data": {"object": {"customer": "cus_stripe_9"}}}).encode()
t = str(int(time.time())); s3 = hmac.new(b"whsec_teste", t.encode() + b"." + b2, hashlib.sha256).hexdigest()
st, j = req("POST", "/cobranca/stripe", b2, {"Stripe-Signature": f"t={t},v1={s3}"})
check("pagamento reativa cliente suspenso", st == 200 and reg()["clientes"]["beta"]["status"] == "ativo", (st, j))

# ---------- painel ----------
TK = {"X-Token": "token-do-operador-123456"}
st, _ = req("GET", "/api/clientes")
check("API do painel sem token -> 401", st == 401)
st, j = req("GET", "/api/clientes", None, {"X-Token": "x"})
check("API do painel com token errado -> 401", st == 401)
st, j = req("GET", "/api/clientes", None, TK)
check("painel lista clientes e eventos", st == 200 and {c["slug"] for c in j["clientes"]} == {"acme", "beta"} and j["eventos"], j)
st, h = req("GET", "/painel")
check("página do painel abre localmente", st == 200 and "Painel do operador" in h)
st, j = req("POST", "/api/tolerancia", {"slug": "acme", "dias": 9}, TK)
check("painel altera tolerância", st == 200 and reg()["clientes"]["acme"]["tolerancia_dias"] == 9, j)
st, j = req("POST", "/api/tolerancia", {"slug": "acme", "dias": 99}, TK)
check("tolerância fora do limite -> 400", st == 400)
st, j = req("POST", "/api/suspender", {"slug": "acme"}, TK)
check("painel suspende", st == 200 and reg()["clientes"]["acme"]["status"] == "suspenso")
st, j = req("POST", "/api/renovar", {"slug": "acme", "dias": 15}, TK)
check("painel renova e reativa", st == 200 and reg()["clientes"]["acme"]["status"] == "ativo", j)
st, j = req("POST", "/api/renovar", {"slug": "naoexiste"}, TK)
check("cliente inexistente -> 400 (sem derrubar o servidor)", st == 400)
st, j = req("POST", "/api/vincular", {"slug": "acme", "provedor": "stripe", "cliente_id": "cus_stripe_9"}, TK)
check("painel recusa identificador já usado", st == 400 and "já ligado" in j["erro"], j)
st, j = req("POST", "/api/rotina", {}, TK)
check("painel roda a rotina", st == 200)
st, _ = req("GET", "/saude")
check("/saude responde", st == 200)
st, _ = req("POST", "/cobranca/asaas", b"x" * (300 * 1024), {"asaas-access-token": "asaas-tok-xyz"})
check("corpo grande demais -> 413", st == 413)
st, j = req("POST", "/cobranca/asaas", b"{nao json", {"asaas-access-token": "asaas-tok-xyz"})
check("JSON inválido -> 400", st == 400)


# ---------- painel: criar / senha / backup / reiniciar / remover ----------
def cmdlog(): return [" ".join(c[0]) for c in A.CMDLOG]
A.CMDLOG.clear()
st, j = req("POST", "/api/novo", {"slug": "gama", "nome": "Gama Ltda", "provider": "official", "dias": "20", "tolerancia": "4", "anthropic_key": "sk-ant-SEGREDO", "wa_token": "wt", "wa_phone_id": "1", "meta_secret": "ms"}, TK)
check("painel cria cliente (oficial) e devolve a senha", st == 200 and "DASH_TOKEN" in j["msg"] and reg()["clientes"]["gama"]["tolerancia_dias"] == 4, (st, j))
check("cliente criado sobe no Docker", any("up -d" in c for c in cmdlog()), cmdlog())
check("chave do cliente vai para o .env e não para o histórico", "sk-ant-SEGREDO" in (tmp / "clientes" / "gama" / ".env").read_text() and "sk-ant-SEGREDO" not in (tmp / "cobranca-log.jsonl").read_text())
st, j = req("POST", "/api/novo", {"slug": "qrcli", "provider": "qr"}, TK)
check("QR sem aceite do risco é recusado", st == 400 and "QR" in j["erro"] and "qrcli" not in reg()["clientes"], j)
st, j = req("POST", "/api/novo", {"slug": "qrcli", "provider": "qr", "aceito_risco_qr": True}, TK)
check("QR com aceite é criado e registra a data", st == 200 and reg()["clientes"]["qrcli"].get("risco_qr_aceito_em"), (st, j))
st, j = req("POST", "/api/novo", {"slug": "gama", "provider": "official"}, TK)
check("nome repetido -> 400", st == 400)
st, j = req("POST", "/api/novo", {"slug": "../x", "provider": "official"}, TK)
check("nome com caracteres perigosos -> 400", st == 400)
st, j = req("POST", "/api/novo", {"slug": "zz", "provider": "xx"}, TK)
check("modo inválido -> 400", st == 400)
st, j = req("POST", "/api/token", {"slug": "gama"}, TK)
dash = reg() and (tmp / "clientes" / "gama" / ".env").read_text().split("DASH_TOKEN=")[1].split()[0]
check("painel mostra a senha do cliente", st == 200 and j["msg"] == dash, j)
check("ver a senha fica no registro de ações", any(e["tipo"] == "senha_vista" for e in C.recent_log()))
A.CMDLOG.clear()
st, j = req("POST", "/api/backup", {"slug": "gama"}, TK)
check("backup copia do contêiner para pasta do servidor", st == 200 and any("docker cp sdr-gama:/data/backups/." in c and "backups-painel" in c for c in cmdlog()), (st, j, cmdlog()))
st, j = req("POST", "/api/reiniciar", {"slug": "gama"}, TK)
check("reiniciar", st == 200 and any("force-recreate" in c for c in cmdlog()))
st, j = req("POST", "/api/remover", {"slug": "gama"}, TK)
check("remover sem confirmação -> 400 e cliente continua", st == 400 and "gama" in reg()["clientes"])
st, j = req("POST", "/api/remover", {"slug": "gama", "confirmacao": "outro"}, TK)
check("remover com nome errado -> 400", st == 400 and "gama" in reg()["clientes"])
st, j = req("POST", "/api/remover", {"slug": "gama", "confirmacao": "gama"}, TK)
check("remover com o nome certo apaga cliente e pasta", st == 200 and "gama" not in reg()["clientes"] and not (tmp / "clientes" / "gama").exists(), (st, j))
st, _ = req("POST", "/api/remover", {"slug": "qrcli", "confirmacao": "qrcli"}, {})
check("sem token nenhuma ação destrutiva passa", st == 401 and "qrcli" in reg()["clientes"])
check("criação e remoção ficam registradas", {"criado", "removido", "backup"} <= {e["tipo"] for e in C.recent_log(100)})

srv.shutdown()
print(f"\n{OK} ok, {FAIL} falha(s)")
sys.exit(1 if FAIL else 0)
