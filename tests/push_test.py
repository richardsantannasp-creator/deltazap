"""App no celular: cifra do aviso (vetor oficial da RFC 8291), VAPID, inscrições, gatilhos, privacidade e arquivos do PWA."""
import asyncio, base64, json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
def q(S, sql, *a):
    with S.conn() as c: return [dict(r) for r in c.execute(sql, a)]
def run(S, sql, *a):
    with S.conn() as c: c.execute(sql, a)
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0
def u(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
def e(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def priv_from(raw): return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
def pub_of(k): return k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

def decrypt(body, ua_priv, auth):
    """Lado do navegador (RFC 8291), escrito à parte para conferir a cifra."""
    salt, rs, idlen = body[:16], int.from_bytes(body[16:20], "big"), body[20]
    as_pub, ct = body[21:21 + idlen], body[21 + idlen:]
    shared = ua_priv.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = HKDF(hashes.SHA256(), 32, auth, b"WebPush: info\x00" + pub_of(ua_priv) + as_pub).derive(shared)
    cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    pt = AESGCM(cek).decrypt(nonce, ct, None)
    assert pt.endswith(b"\x02") and rs == 4096
    return pt[:-1]

def new_device(host):
    k = ec.generate_private_key(ec.SECP256R1()); auth = os.urandom(16)
    return {"priv": k, "auth": auth, "endpoint": f"https://{host}/push/" + e(os.urandom(8)), "keys": {"p256dh": e(pub_of(k)), "auth": e(auth)}}

async def settle(): await asyncio.sleep(0.15)
def to(dev): return [x for x in harness.PUSHLOG if x["url"] == dev["endpoint"]]
def msgs(dev): return [json.loads(decrypt(x["body"], dev["priv"], dev["auth"])) for x in to(dev)]

async def main():
    S = harness.load_server(); S.PROVIDER = "qr"; S.LINES_MAX = 4
    harness.GW["state"] = "open"
    # ---------- cifra: vetor oficial da RFC 8291 (apêndice A) ----------
    body = S.push_encrypt(b"When I grow up, I want to be a watermelon", u("BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"),
                          u("BTBZMqHH6r4Tts7J_aSIgg"), as_private=priv_from(u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw")), salt=u("DGv6ra1nlYgDCS1FRnbzlw"))
    want = ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml" "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
            "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")
    check("cifra idêntica ao vetor oficial da RFC 8291", e(body) == want, e(body))
    dev0 = new_device("fcm.push.test")
    b2 = S.push_encrypt("Olá, ação ✓".encode(), pub_of(dev0["priv"]), dev0["auth"])
    check("aviso aleatório é decifrado pelo navegador", decrypt(b2, dev0["priv"], dev0["auth"]).decode() == "Olá, ação ✓")
    check("cada envio usa chave e sal novos", S.push_encrypt(b"x", pub_of(dev0["priv"]), dev0["auth"]) != S.push_encrypt(b"x", pub_of(dev0["priv"]), dev0["auth"]))
    # ---------- VAPID ----------
    k1 = S.vapid_keys(); k2 = S.vapid_keys()
    check("chaves VAPID são geradas uma vez e guardadas", k1 == k2 and len(u(k1["pub"])) == 65 and len(u(k1["priv"])) == 32)
    check("a chave pública é aberta (sem login) e é a mesma", (await S.push_key())["key"] == k1["pub"])
    h = S.vapid_header("https://fcm.push.test/push/abc")
    t = h.split("t=")[1].split(",")[0]; hd, bd, sg = t.split(".")
    claims = json.loads(u(bd)); sig = u(sg)
    pubk = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), u(k1["pub"]))
    try:
        pubk.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")), f"{hd}.{bd}".encode(), ec.ECDSA(hashes.SHA256())); sigok = True
    except Exception as ex: sigok = False
    check("assinatura VAPID (ES256) confere com a chave pública", sigok and len(sig) == 64)
    check("VAPID: destino, validade e contato", claims["aud"] == "https://fcm.push.test" and 0 < claims["exp"] - time.time() <= 12 * 3600 + 5 and claims["sub"].startswith("mailto:"), claims)
    check("VAPID: cabeçalho leva a chave pública", f"k={k1['pub']}" in h)
    # ---------- equipe e inscrições ----------
    S.set_setting("qr_ack", json.dumps({"version": S.QR_TERMS_VERSION, "ts": time.time()}))
    await S.pacing_put({"reply_delay_min": 0, "reply_delay_max": 0, "start_hour": 0, "end_hour": 24, "weekdays_only": False})
    S._agent_create(S.AgentIn(login="rita", name="Rita", password="abcdef"), 0)
    await S.managers_add(S.ManagerIn(login="gil", name="Gil G", password="senhaforte1"))
    S._agent_create(S.AgentIn(login="duda", name="Duda", password="abcdef"), 1)
    S.set_setting("handoff", json.dumps({"auto_assign": True, "wait_min": 15, "fallback": "manter", "reassign_min": 10}))
    ag = {r["login"]: r["id"] for r in q(S, "SELECT id,login FROM agents")}
    tr = (await S.agent_login(S.AgentLoginIn(login="rita", password="abcdef")))["token"]
    td = (await S.agent_login(S.AgentLoginIn(login="duda", password="abcdef")))["token"]
    tg = (await S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1")))["token"]
    rita, duda, gil = new_device("fcm.push.test"), new_device("web.push.test"), new_device("updates.push.test")
    PI = lambda d: S.PushIn(endpoint=d["endpoint"], keys=d["keys"])
    check("inscrição sem https é recusada", await err(S.agent_push_on(S.PushIn(endpoint="http://x/y", keys=rita["keys"]), x_token=tr)) == 400)
    check("inscrição sem chaves é recusada", await err(S.agent_push_on(S.PushIn(endpoint=rita["endpoint"], keys={}), x_token=tr)) == 400)
    check("sem login não inscreve", await err(S.agent_push_on(PI(rita), x_token="")) == 401)
    await S.agent_push_on(PI(rita), x_token=tr); await S.agent_push_on(PI(duda), x_token=td); await S.gestor_push_on(PI(gil), x_token=tg)
    check("3 aparelhos inscritos", len(q(S, "SELECT * FROM push_subs")) == 3)
    await S.agent_push_on(PI(rita), x_token=tr)
    check("inscrever de novo não duplica", len(q(S, "SELECT * FROM push_subs WHERE endpoint=?", rita["endpoint"])) == 1)
    # ---------- gatilhos ----------
    run(S, "UPDATE agents SET last_seen=?, available=1", time.time())
    await S.handle_incoming("5521955550001", "Marcos Souza", "quero um plano", "p1", line="main")
    harness.PUSHLOG.clear()
    S.exec_tool("5521955550001", "transferir_para_humano", {"motivo": "preço"}); await settle()
    L = S.get_lead("5521955550001")
    who = {ag["rita"]: rita, ag["duda"]: duda}.get(L["agent_id"])
    check("transferência avisa só o atendente que recebeu (equipe do administrador)", L["agent_id"] == ag["rita"] and len(to(rita)) == 1 and not to(duda) and not to(gil), (L["agent_id"], len(harness.PUSHLOG)))
    m = msgs(rita)[0]
    check("aviso: título, nome do lead e destino", m["title"] == "Nova conversa" and "Marcos" in m["body"] and m["url"] == "/atendente", m)
    check("o aviso NÃO leva o texto da mensagem nem o telefone", "plano" not in json.dumps(m) and "5521955550001" not in m["body"], m)
    check("a requisição leva VAPID, cifra e TTL", "vapid t=" in to(rita)[0]["headers"]["Authorization"] and to(rita)[0]["headers"]["Content-Encoding"] == "aes128gcm" and to(rita)[0]["headers"]["TTL"] == "3600")
    # lead escreve durante o atendimento
    harness.PUSHLOG.clear()
    await S.handle_incoming("5521955550001", "Marcos Souza", "e o valor?", "p2"); await settle()
    check("mensagem do lead durante o atendimento avisa o atendente", len(to(rita)) == 1 and msgs(rita)[0]["title"] == "Nova mensagem")
    await S.handle_incoming("5521955550001", "Marcos Souza", "alô?", "p3"); await settle()
    check("avisos seguidos do mesmo lead são agrupados (20 s)", len(to(rita)) == 1)
    S.PUSH_LAST.clear()
    # conversa de número do gestor
    run(S, "INSERT INTO lines(id,label,active,created,manager_id) VALUES('gil-1','Gil',1,?,1)", time.time())
    await S.handle_incoming("5521955550002", "Ana Paula", "oi", "p4", line="gil-1")
    harness.PUSHLOG.clear()
    S.exec_tool("5521955550002", "transferir_para_humano", {"motivo": "x"}); await settle()
    check("número do gestor: o aviso vai para a equipe do gestor, não para a do administrador", len(to(duda)) == 1 and not to(rita) and S.get_lead("5521955550002")["agent_id"] == ag["duda"])
    # fila com ninguém disponível: avisa o gestor
    run(S, "UPDATE agents SET available=0 WHERE manager_id=1")
    await S.handle_incoming("5521955550003", "Beto Lima", "oi", "p5", line="gil-1")
    harness.PUSHLOG.clear()
    S.exec_tool("5521955550003", "transferir_para_humano", {"motivo": "x"}); await settle()
    gm = msgs(gil)
    check("sem atendente disponível, o gestor é avisado da fila", len(gm) == 1 and gm[0]["title"] == "Conversa na fila" and gm[0]["url"] == "/gestor" and not to(rita), gm)
    # lead novo na fila do administrador sem ninguém online
    run(S, "UPDATE agents SET available=0 WHERE manager_id=0")
    # gestor assume e o lead escreve
    S.PUSH_LAST.clear()
    await S.gestor_takeover("5521955550003", S.TakeIn(human=True), x_token=tg)
    harness.PUSHLOG.clear()
    await S.handle_incoming("5521955550003", "Beto Lima", "obrigado", "p6"); await settle()
    check("conversa com o gestor: ele é avisado quando o lead escreve", len(to(gil)) == 1 and msgs(gil)[-1]["title"] == "Nova mensagem")
    # ---------- limpeza ----------
    gone = new_device("gone.push.test"); await S.agent_push_on(PI(gone), x_token=tr)
    S.PUSH_LAST.clear(); n = await S.push_notify("agent", [ag["rita"]], "t", "b", "/atendente", "x")
    check("aparelho que o navegador diz que não existe mais (410) é removido", not q(S, "SELECT 1 FROM push_subs WHERE endpoint=?", gone["endpoint"]) and q(S, "SELECT 1 FROM push_subs WHERE endpoint=?", rita["endpoint"]))
    await S.agent_push_off(S.PushIn(endpoint=rita["endpoint"]), x_token=tr)
    check("desligar os avisos remove a inscrição", not q(S, "SELECT 1 FROM push_subs WHERE endpoint=?", rita["endpoint"]))
    await S.agent_push_off(S.PushIn(endpoint=duda["endpoint"]), x_token=tr)
    check("atendente não remove aparelho de outro", q(S, "SELECT 1 FROM push_subs WHERE endpoint=?", duda["endpoint"]))
    await S.agent_push_on(PI(duda), x_token=tr)
    check("o mesmo aparelho passa para o novo usuário ao entrar", q(S, "SELECT owner_id FROM push_subs WHERE endpoint=?", duda["endpoint"])[0]["owner_id"] == ag["rita"])
    # ---------- arquivos do app ----------
    sw = await S.service_worker()
    swb = sw.body if hasattr(sw, "body") else sw.content
    swt = swb.decode() if isinstance(swb, bytes) else swb
    check("service worker trata push e clique", "addEventListener('push'" in swt and "notificationclick" in swt and "showNotification" in swt)
    f = os.path.join(tempfile.mkdtemp(), "sw.js"); open(f, "w").write(swt)
    ck = subprocess.run(["node", "--check", f], capture_output=True, text=True)
    check("service worker: JavaScript válido", ck.returncode == 0, ck.stderr)
    for nm, fn, st in (("atendente", S.manifest_atendente, "/atendente"), ("gestor", S.manifest_gestor, "/gestor")):
        r = await fn(); mb = r.body if hasattr(r, "body") else r.content
        mj = json.loads(mb)
        check(f"manifesto do {nm}: instalável (standalone, início, ícones 192 e 512)", mj["display"] == "standalone" and mj["start_url"] == st and {i["sizes"] for i in mj["icons"]} == {"192x192", "512x512"}, mj)
    from PIL import Image
    for sz in (192, 512):
        im = Image.open(os.path.join(S.HERE, "static", f"icon-{sz}.png"))
        check(f"ícone {sz}x{sz} existe", im.size == (sz, sz))
    check("ícone de tamanho inexistente: 404", await err(S.app_icon(100)) == 404)
    for fnm in ("atendente.html", "gestor.html"):
        h = open(os.path.join(S.HERE, fnm), encoding="utf-8").read()
        check(f"{fnm}: manifesto, ícone, botão de avisos e service worker", all(x in h for x in ('rel="manifest"', 'apple-touch-icon', 'id="pushb"', '"/sw.js"', "/api/push/key")))
    dk = open(os.path.join(S.HERE, "Dockerfile")).read()
    check("Dockerfile copia gestor.html e a pasta static", "gestor.html" in dk and "COPY static" in dk)
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
