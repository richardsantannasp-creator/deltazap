#!/usr/bin/env python3
"""Receptor de pagamentos + painel do operador (stdlib, sem dependências).

Roda no servidor do operador, ao lado do sdr-admin.py:
  - POST /cobranca/asaas | /cobranca/stripe | /cobranca/generico  -> pagamento confirmado renova a assinatura sozinho
  - /painel  (só acessível de dentro do servidor, com token)       -> lista clientes, renova, suspende, retoma
  - a cada 6 h roda a rotina de vencimentos (avisos graduais + suspensão após a tolerância)

Segredos por variável de ambiente (nunca na linha de comando):
  OPERADOR_TOKEN          senha do painel (obrigatória)
  ASAAS_WEBHOOK_TOKEN     token que você cadastra no webhook do Asaas (cabeçalho asaas-access-token)
  STRIPE_WEBHOOK_SECRET   whsec_... do endpoint do Stripe (cabeçalho Stripe-Signature)
  PAY_HMAC_SECRET         segredo para o formato genérico (cabeçalho X-Signature = HMAC-SHA256 hex do corpo)
Só os provedores com segredo configurado aceitam eventos; os demais respondem 404.
"""
import argparse, contextlib, io, hashlib, hmac, importlib.util, ipaddress, json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sdr_admin", HERE / "sdr-admin.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)
A.RAISE = True

LOCK = threading.Lock()
MAX_BODY = 256 * 1024
STRIPE_TOL = 300
PAID = {"asaas": {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}, "stripe": {"invoice.paid", "invoice.payment_succeeded"}}
CFG = {"operador_token": "", "asaas": "", "stripe": "", "generico": ""}


def cfg_from_env():
    CFG["operador_token"] = os.getenv("OPERADOR_TOKEN", "")
    CFG["asaas"] = os.getenv("ASAAS_WEBHOOK_TOKEN", "")
    CFG["stripe"] = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    CFG["generico"] = os.getenv("PAY_HMAC_SECRET", "")


def eq(a, b):
    return hmac.compare_digest(str(a).encode(), str(b).encode())


# ---------- registro de eventos (idempotência + histórico) ----------
def ev_path():
    return A.ROOT / "cobranca-eventos.json"


def log_path():
    return A.ROOT / "cobranca-log.jsonl"


def seen(eid):
    try:
        return eid in json.loads(ev_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return False


def mark(eid):
    try:
        ids = json.loads(ev_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        ids = []
    ids.append(eid)
    tmp = ev_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(ids[-5000:]), encoding="utf-8")
    os.replace(tmp, ev_path())


def log(kind, **kw):
    A.ROOT.mkdir(parents=True, exist_ok=True)
    row = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "tipo": kind, **kw}
    with open(log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def recent_log(n=40):
    try:
        lines = log_path().read_text(encoding="utf-8").splitlines()[-n:]
    except FileNotFoundError:
        return []
    return [json.loads(x) for x in reversed(lines)]


# ---------- verificação e interpretação de cada provedor ----------
def verify_asaas(headers, body):
    return bool(CFG["asaas"]) and eq(headers.get("asaas-access-token", ""), CFG["asaas"])


def verify_stripe(headers, body, now=None):
    if not CFG["stripe"]:
        return False
    parts = dict(p.split("=", 1) for p in headers.get("stripe-signature", "").split(",") if "=" in p)
    t, v1 = parts.get("t", ""), parts.get("v1", "")
    if not t.isdigit() or abs((now or time.time()) - int(t)) > STRIPE_TOL:
        return False
    exp = hmac.new(CFG["stripe"].encode(), t.encode() + b"." + body, hashlib.sha256).hexdigest()
    return eq(v1, exp)


def verify_generico(headers, body):
    if not CFG["generico"]:
        return False
    exp = hmac.new(CFG["generico"].encode(), body, hashlib.sha256).hexdigest()
    return eq(headers.get("x-signature", "").lower(), exp)


def interpret(prov, data):
    """-> (id_do_evento, pagamento_confirmado, cliente_do_provedor, slug_direto, dias)"""
    if prov == "asaas":
        ev = data.get("event", "")
        pay = data.get("payment") or {}
        eid = data.get("id") or f"{ev}:{pay.get('id', '')}"
        return str(eid), ev in PAID["asaas"], pay.get("customer", ""), None, None
    if prov == "stripe":
        obj = (data.get("data") or {}).get("object") or {}
        return str(data.get("id", "")), data.get("type") in PAID["stripe"], obj.get("customer", ""), None, None
    dias = data.get("dias")
    return str(data.get("id", "")), data.get("status", "pago") == "pago", "", data.get("cliente") or data.get("slug"), dias if isinstance(dias, int) else None


def process(prov, data):
    """Aplica um evento já verificado. Devolve (http, mensagem)."""
    eid, pago, cust, slug, dias = interpret(prov, data)
    if not eid:
        return 400, "evento sem identificador"
    with LOCK:
        if seen(eid):
            return 200, "duplicado (já processado)"
        if not pago:
            mark(eid)
            return 200, "ignorado (não é pagamento confirmado)"
        reg = A.load_reg()
        if not slug:
            slug = next((k for k, c in reg["clientes"].items() if cust and c.get("cobranca", {}).get(prov) == cust), None)
        if not slug or slug not in reg["clientes"]:
            log("sem_vinculo", provedor=prov, evento=eid, cliente_provedor=cust)
            return 202, "pagamento sem cliente vinculado (veja o painel)"
        if dias is not None and not (1 <= dias <= 400):
            return 400, "dias fora do limite"
        try:
            novo, reativou = A.renovar_cliente(slug, dias=dias)
        except SystemExit as e:
            log("erro", provedor=prov, evento=eid, cliente=slug, erro=getattr(e, "msg", str(e)))
            return 500, "falha ao renovar"
        mark(eid)
        log("renovado", provedor=prov, evento=eid, cliente=slug, valido_ate=novo.isoformat(), reativado=reativou)
        return 200, f"{slug} renovado até {novo.isoformat()}"


# ---------- ações do painel ----------
def clientes_view():
    reg = A.load_reg()
    out = []
    for slug, c in sorted(reg["clientes"].items()):
        out.append({"slug": slug, "nome": c.get("nome", ""), "dominio": c.get("dominio", ""), "modo": c.get("provider", ""), "status": c["status"],
                    "valido_ate": c.get("valido_ate", ""), "dias": A.days_left(c), "tolerancia": c.get("tolerancia_dias", 3),
                    "periodo": c.get("periodo_dias", 30), "cobranca": c.get("cobranca", {})})
    return out


def acao(nome, d):
    slug = d.get("slug", "")
    with LOCK:
        if nome == "renovar":
            dias = d.get("dias")
            novo, re_ = A.renovar_cliente(slug, dias=int(dias) if dias else None)
            log("renovado", provedor="painel", cliente=slug, valido_ate=novo.isoformat(), reativado=re_)
            return f"{slug} válido até {novo.isoformat()}"
        if nome == "suspender":
            A._set_status(slug, "suspenso"); log("suspenso", provedor="painel", cliente=slug); return f"{slug} suspenso"
        if nome == "retomar":
            A._set_status(slug, "ativo"); A.set_notice(slug, None); log("retomado", provedor="painel", cliente=slug); return f"{slug} reativado"
        if nome == "tolerancia":
            t = int(d.get("dias", -1))
            if not 0 <= t <= 30:
                raise ValueError("tolerância deve ficar entre 0 e 30 dias")
            reg = A.load_reg(); A.get_client(reg, slug)["tolerancia_dias"] = t; A.save_reg(reg); return f"{slug}: tolerância de {t} dia(s)"
        if nome == "vincular":
            prov = d.get("provedor")
            if prov not in ("asaas", "stripe") or not d.get("cliente_id"):
                raise ValueError("informe provedor (asaas|stripe) e o identificador do cliente")
            reg = A.load_reg(); c = A.get_client(reg, slug)
            for o, oc in reg["clientes"].items():
                if o != slug and oc.get("cobranca", {}).get(prov) == d["cliente_id"]:
                    raise ValueError(f"identificador já ligado a '{o}'")
            c.setdefault("cobranca", {})[prov] = d["cliente_id"]; A.save_reg(reg); return f"{slug} ligado ao {prov}"
        if nome in ("novo", "remover", "backup", "token", "reiniciar"):
            return admin_cmd(nome, d)
        if nome == "rotina":
            sus, breve = A.rotina_vencimentos()
            return f"suspensos: {', '.join(sus) or 'nenhum'}; vencem em breve: {', '.join(breve) or 'nenhum'}"
    raise ValueError("ação desconhecida")


def admin_cmd(nome, d):
    """Ações do sdr-admin chamadas pelo painel. A saída (que pode conter senhas) volta só para quem está logado e nunca vai para o registro."""
    import types
    slug = str(d.get("slug", "")).strip()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if nome == "novo":
            ns = types.SimpleNamespace(slug=slug, nome=d.get("nome") or None, provider=d.get("provider"), dominio=d.get("dominio") or None,
                                       dias=int(d["dias"]) if str(d.get("dias") or "").strip() else None, ate=None, anthropic_key=d.get("anthropic_key") or None,
                                       wa_token=d.get("wa_token") or None, wa_phone_id=d.get("wa_phone_id") or None, meta_secret=d.get("meta_secret") or None,
                                       obs=d.get("obs") or None, aceito_risco_qr=bool(d.get("aceito_risco_qr")),
                                       tolerancia=int(d.get("tolerancia") or 3), periodo_dias=int(d.get("periodo_dias") or 30))
            if ns.provider not in ("qr", "official"):
                raise ValueError("escolha o modo: qr ou official")
            A.cmd_novo(ns)
            log("criado", provedor="painel", cliente=slug, modo=ns.provider)
        elif nome == "remover":
            if str(d.get("confirmacao", "")) != slug or not slug:
                raise ValueError("para remover, digite o nome exato do cliente na confirmação")
            A.cmd_remover(types.SimpleNamespace(slug=slug, confirmo_apagar_dados=True))
            log("removido", provedor="painel", cliente=slug)
        elif nome == "backup":
            dest = A.ROOT / "backups-painel" / time.strftime("%Y%m%d-%H%M%S")
            A.cmd_backup(types.SimpleNamespace(slug=slug, todos=False, destino=str(dest)))
            log("backup", provedor="painel", cliente=slug)
        elif nome == "token":
            A.cmd_token(types.SimpleNamespace(slug=slug))
            log("senha_vista", provedor="painel", cliente=slug)
        elif nome == "reiniciar":
            A.cmd_reiniciar(types.SimpleNamespace(slug=slug))
            log("reiniciado", provedor="painel", cliente=slug)
    return buf.getvalue().strip() or "feito"


PAGE = """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Painel do operador</title>
<style>[hidden]{display:none!important}body{font:15px system-ui;margin:0;background:#f6f7f9;color:#1b1f24}main{max-width:1000px;margin:0 auto;padding:16px}h1{font-size:20px}table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px}
th,td{padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;font-size:14px}th{font-size:12px;text-transform:uppercase;color:#667}button{padding:5px 10px;margin:2px;border:1px solid #c5cad3;border-radius:6px;background:#fff;cursor:pointer}
.s-ativo{color:#0a7d33}.s-suspenso{color:#b42318}.v{color:#b42318;font-weight:600}#msg{min-height:22px;margin:8px 0}#login{margin:40px auto;max-width:320px}input{padding:7px;width:100%;box-sizing:border-box}
.log{font:12px ui-monospace,monospace;background:#fff;border-radius:8px;padding:8px;max-height:240px;overflow:auto}</style>
<main><h1>Painel do operador</h1><div id="login"><p>Token do operador</p><input id="tk" type="password"><p><button id="go">Entrar</button></p></div>
<div id="app" hidden><div id="msg"></div><pre id="out" hidden style="background:#fff;padding:10px;border-radius:8px;white-space:pre-wrap;word-break:break-all"></pre>
<p><button id="rot">Rodar rotina de vencimentos agora</button> <button id="nw">Novo cliente</button></p>
<form id="nf" hidden style="background:#fff;padding:12px;border-radius:8px;margin-bottom:12px;display:grid;gap:6px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
<label>Nome curto (ex.: acme)<input name="slug" required></label><label>Nome da empresa<input name="nome"></label>
<label>Modo<select name="provider"><option value="official">API oficial (recomendado)</option><option value="qr">QR Code (risco de banimento)</option></select></label>
<label>Dias de validade<input name="dias" type="number" value="30"></label><label>Tolerância (dias)<input name="tolerancia" type="number" value="3"></label>
<label>Chave Anthropic do cliente<input name="anthropic_key" type="password" autocomplete="off"></label>
<label>WhatsApp token (oficial)<input name="wa_token" type="password" autocomplete="off"></label><label>WhatsApp phone id (oficial)<input name="wa_phone_id"></label>
<label>Meta app secret (oficial)<input name="meta_secret" type="password" autocomplete="off"></label>
<label style="grid-column:1/-1"><input type="checkbox" name="aceito_risco_qr" style="width:auto"> Se QR: o cliente foi informado por escrito e aceitou o risco de banimento do número</label>
<div><button type="submit">Criar cliente</button></div></form>
<table><thead><tr><th>Cliente</th><th>Modo</th><th>Estado</th><th>Válido até</th><th>Dias</th><th>Tolerância</th><th>Cobrança</th><th>Ações</th></tr></thead><tbody id="rows"></tbody></table>
<h2 style="font-size:16px">Últimos eventos</h2><div class="log" id="log"></div></div></main>
<script>
let TK=sessionStorage.getItem('optk')||'';const $=i=>document.getElementById(i);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(p,b){const r=await fetch(p,{method:b?'POST':'GET',headers:{'X-Token':TK,'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});
 const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.erro||('erro '+r.status));return j}
function say(t,bad){$('msg').textContent=t;$('msg').style.color=bad?'#b42318':'#0a7d33'}
async function act(n,d){try{const m=(await api('/api/'+n,d)).msg;if(['novo','token','backup'].includes(n)){$('out').textContent=m;$('out').hidden=false;say('Pronto.')}else{$('out').hidden=true;say(m)}load()}catch(e){say(e.message,1)}}
async function load(){try{const j=await api('/api/clientes');$('login').hidden=true;$('app').hidden=false;
 $('rows').innerHTML=j.clientes.map(c=>`<tr><td><b>${esc(c.slug)}</b><br><small>${esc(c.dominio)}</small></td><td>${esc(c.modo)}</td><td class="s-${esc(c.status)}">${esc(c.status)}</td><td>${esc(c.valido_ate)}</td>
 <td class="${c.dias!==null&&c.dias<0?'v':''}">${c.dias===null?'-':c.dias}</td><td>${c.tolerancia} d</td><td><small>${esc(Object.entries(c.cobranca).map(([k,v])=>k+':'+v).join(' ')||'—')}</small></td>
 <td><button data-a="renovar" data-s="${esc(c.slug)}" data-p="${c.periodo}">Renovar +${c.periodo}d</button>${c.status==='ativo'?`<button data-a="suspender" data-s="${esc(c.slug)}">Suspender</button>`:`<button data-a="retomar" data-s="${esc(c.slug)}">Retomar</button>`}
 <button data-a="tolerancia" data-s="${esc(c.slug)}">Tolerância</button><button data-a="vincular" data-s="${esc(c.slug)}">Vincular</button>
 <button data-a="token" data-s="${esc(c.slug)}">Senha</button><button data-a="backup" data-s="${esc(c.slug)}">Backup</button><button data-a="reiniciar" data-s="${esc(c.slug)}">Reiniciar</button><button data-a="remover" data-s="${esc(c.slug)}">Remover</button></td></tr>`).join('')||'<tr><td colspan=8>Nenhum cliente.</td></tr>';
 $('log').innerHTML=j.eventos.map(e=>esc(e.t+'  '+e.tipo+'  '+(e.cliente||e.cliente_provedor||'')+'  '+(e.provedor||'')+(e.valido_ate?'  até '+e.valido_ate:''))).join('<br>')||'sem eventos'}
 catch(e){sessionStorage.removeItem('optk');$('login').hidden=false;$('app').hidden=true}}
$('go').onclick=()=>{TK=$('tk').value;sessionStorage.setItem('optk',TK);load()};
$('rot').onclick=()=>act('rotina',{});
$('nw').onclick=()=>{$('nf').hidden=!$('nf').hidden};
$('nf').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData($('nf')));d.aceito_risco_qr=$('nf').aceito_risco_qr.checked;await act('novo',d);if($('msg').style.color!=='rgb(180, 35, 24)'){$('nf').reset();$('nf').hidden=true}};
$('rows').onclick=e=>{const b=e.target.closest('button');if(!b)return;const a=b.dataset.a,s=b.dataset.s;
 if(a==='renovar')act('renovar',{slug:s,dias:b.dataset.p});else if(a==='suspender'){if(confirm('Suspender '+s+'? O sistema do cliente para de responder.'))act('suspender',{slug:s})}
 else if(a==='retomar')act('retomar',{slug:s});else if(a==='tolerancia'){const v=prompt('Dias de tolerância após o vencimento (0 a 30):');if(v!==null)act('tolerancia',{slug:s,dias:v})}
 else if(a==='token'||a==='backup'||a==='reiniciar')act(a,{slug:s});else if(a==='remover'){const c=prompt('Isto APAGA todos os dados de '+s+', sem volta. Faça backup antes. Digite o nome do cliente para confirmar:');if(c)act('remover',{slug:s,confirmacao:c})}
 else if(a==='vincular'){const p=prompt('Provedor (asaas ou stripe):');const i=p&&prompt('Identificador do cliente no provedor (ex.: cus_123):');if(p&&i)act('vincular',{slug:s,provedor:p,cliente_id:i})}};
if(TK)load();
</script></html>"""


class H(BaseHTTPRequestHandler):
    server_version = "sdr-cobranca"

    def log_message(self, *a):
        pass

    def send(self, code, obj, ctype="application/json"):
        raw = obj.encode() if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def local_ok(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

    def admin_ok(self):
        return bool(CFG["operador_token"]) and self.local_ok() and eq(self.headers.get("X-Token", ""), CFG["operador_token"])

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return None
        return self.rfile.read(n)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/painel":
            if not self.local_ok():
                return self.send(404, {"erro": "não encontrado"})
            return self.send(200, PAGE, "text/html")
        if path == "/api/clientes":
            if not self.admin_ok():
                return self.send(401, {"erro": "token inválido"})
            return self.send(200, {"clientes": clientes_view(), "eventos": recent_log()})
        if path == "/saude":
            return self.send(200, {"ok": True})
        self.send(404, {"erro": "não encontrado"})

    def do_POST(self):
        path = urlparse(self.path).path
        raw = self.body()
        if raw is None:
            return self.send(413, {"erro": "corpo grande demais"})
        if path.startswith("/cobranca/"):
            prov = {"asaas": "asaas", "stripe": "stripe", "generico": "generico"}.get(path.rsplit("/", 1)[1])
            if not prov or not CFG[prov]:
                return self.send(404, {"erro": "não encontrado"})
            ok = {"asaas": verify_asaas, "stripe": verify_stripe, "generico": verify_generico}[prov]({k.lower(): v for k, v in self.headers.items()}, raw)
            if not ok:
                log("rejeitado", provedor=prov, motivo="assinatura inválida")
                return self.send(401, {"erro": "assinatura inválida"})
            try:
                data = json.loads(raw or b"{}")
                assert isinstance(data, dict)
            except (ValueError, AssertionError):
                return self.send(400, {"erro": "JSON inválido"})
            code, msg = process(prov, data)
            return self.send(code, {"msg": msg})
        if path.startswith("/api/"):
            if not self.admin_ok():
                return self.send(401, {"erro": "token inválido"})
            try:
                d = json.loads(raw or b"{}")
                return self.send(200, {"msg": acao(path[5:], d)})
            except (ValueError, KeyError, TypeError) as e:
                return self.send(400, {"erro": str(e)})
            except SystemExit as e:
                return self.send(400, {"erro": getattr(e, "msg", "falhou")})
        self.send(404, {"erro": "não encontrado"})


def rotina_loop(horas):
    while True:
        time.sleep(horas * 3600)
        try:
            with LOCK:
                A.rotina_vencimentos()
        except BaseException as e:  # noqa
            log("erro", erro=f"rotina: {getattr(e, 'msg', e)}")


def make_server(host, port):
    return ThreadingHTTPServer((host, port), H)


def main(argv=None):
    p = argparse.ArgumentParser(description="Receptor de pagamentos e painel do operador")
    p.add_argument("--raiz"); p.add_argument("--simular", action="store_true")
    p.add_argument("--porta", type=int, default=8900)
    p.add_argument("--host", default="0.0.0.0", help="0.0.0.0 para o proxy (Docker) alcançar; o painel só abre para quem está no próprio servidor")
    p.add_argument("--rotina-horas", type=float, default=6)
    a = p.parse_args(argv)
    if a.raiz:
        A.ROOT = Path(a.raiz)
    A.SIM = a.simular
    cfg_from_env()
    if not CFG["operador_token"] or len(CFG["operador_token"]) < 16:
        sys.exit("Defina OPERADOR_TOKEN (mínimo 16 caracteres) no ambiente.")
    if not (CFG["asaas"] or CFG["stripe"] or CFG["generico"]):
        print("Aviso: nenhum segredo de provedor configurado; só o painel funciona.", file=sys.stderr)
    if a.rotina_horas > 0:
        threading.Thread(target=rotina_loop, args=(a.rotina_horas,), daemon=True).start()
    srv = make_server(a.host, a.porta)
    print(f"Receptor em {a.host}:{a.porta}  |  painel: http://127.0.0.1:{a.porta}/painel (via túnel SSH)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
