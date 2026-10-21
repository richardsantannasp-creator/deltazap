"""Kit de piloto: diagnóstico da instalação e alerta de queda do WhatsApp."""
import asyncio, os, sys, tempfile, time, json
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
    S = harness.load_server(); S.PROVIDER = "qr"
    by = lambda d, i: next((c for c in d["checks"] if c["id"] == i), None)
    harness.GW["state"] = "open"
    d = await S.diagnostico()
    check("diagnóstico lista as verificações principais", all(by(d, i) for i in ("token", "claude", "wa_main", "stt", "ffmpeg", "avisos", "orcamento", "nichos", "disco", "backup", "equipe")), [c["id"] for c in d["checks"]])
    check("Claude responde: ok; chamada registrada com o tipo 'diagnostico'", by(d, "claude")["status"] == "ok" and q(S, "SELECT 1 FROM usage WHERE kind=?", "diagnostico"))
    check("WhatsApp conectado: ok e mostra o número", by(d, "wa_main")["status"] == "ok" and "+" in by(d, "wa_main")["detail"])
    check("senha curta do painel gera aviso com orientação", by(d, "token")["status"] == "aviso" and "16" in by(d, "token")["fix"])
    check("sem canal de aviso: aviso, e o alerta de queda explica que não pode ir pelo WhatsApp", by(d, "avisos")["status"] == "aviso" and "WhatsApp" in by(d, "queda")["fix"])
    check("sem erro: pronto para o piloto", d["ready"] and d["summary"]["erro"] == 0, [c for c in d["checks"] if c["status"] == "erro"])
    # falhas
    orig = S.claude.messages.create
    async def boom(**k): raise RuntimeError("401 invalid x-api-key")
    S.claude.messages.create = boom
    d2 = await S.diagnostico(); S.claude.messages.create = orig
    check("chave do Claude inválida: erro com instrução, e 'pronto' fica falso", by(d2, "claude")["status"] == "erro" and "ANTHROPIC_API_KEY" in by(d2, "claude")["fix"] and not d2["ready"])
    old = S.GATEWAY_SECRET; S.GATEWAY_SECRET = "errada"
    d3 = await S.diagnostico(); S.GATEWAY_SECRET = old
    check("senha do conector diferente: erro claro", by(d3, "wa")["status"] == "erro" and "GATEWAY_SECRET" in by(d3, "wa")["detail"] + by(d3, "wa")["fix"], by(d3, "wa"))
    harness.GW["state"] = "qr"
    d4 = await S.diagnostico(); harness.GW["state"] = "open"
    check("número desconectado: aviso pedindo o QR", by(d4, "wa_main")["status"] == "aviso" and "QR" in by(d4, "wa_main")["fix"])
    S.PROVIDER = "official"; S.WA_TOKEN = ""; S.WA_PHONE_ID = ""
    d5 = await S.diagnostico(); S.PROVIDER = "qr"
    check("API oficial sem credenciais: erro listando o que falta", by(d5, "wa")["status"] == "erro" and "WHATSAPP_TOKEN" in by(d5, "wa")["detail"], by(d5, "wa"))
    S.shutil.which = lambda n: None
    d6 = await S.diagnostico()
    check("sem ffmpeg: aviso", by(d6, "ffmpeg")["status"] == "aviso")
    import shutil as _sh; S.shutil.which = _sh.which
    S.set_setting("handoff", "{}")
    # alerta de queda
    os.environ["NOTIFY_WEBHOOK_URL"] = "https://hooks.example/queda"
    S.set_setting("alerts", json.dumps({**S.get_alerts_cfg(), "whatsapp_to": "5521988880001"}))
    harness.HOOKS.clear(); harness.SENT.clear(); S.CONN_DOWN.clear()
    harness.GW["state"] = "qr"
    await S.conn_watch()
    check("número que nunca conectou não gera alerta (instalação em andamento)", not harness.HOOKS)
    harness.GW["state"] = "open"; await S.conn_watch()
    check("conectado: registra que já esteve no ar", S.get_setting("conn_seen_main") == "1")
    harness.GW["state"] = "close"; await S.conn_watch()
    check("queda recente: ainda não avisa (tolerância)", not harness.HOOKS and "main" in S.CONN_DOWN)
    S.CONN_DOWN["main"]["since"] = time.time() - 3600
    await S.conn_watch()
    txt = json.dumps(harness.HOOKS, ensure_ascii=False)
    check("queda de mais de 5 min: avisa por webhook com o motivo", len(harness.HOOKS) == 1 and "fora do ar" in txt, txt[:200])
    check("o aviso de queda NÃO usa o WhatsApp (ele é o que caiu)", not harness.SENT)
    await S.conn_watch()
    check("não repete o aviso a cada minuto", len(harness.HOOKS) == 1)
    harness.GW["state"] = "open"; await S.conn_watch()
    txt = json.dumps(harness.HOOKS, ensure_ascii=False)
    check("voltou: avisa a reconexão uma vez", len(harness.HOOKS) == 2 and "voltou a funcionar" in txt and "main" not in S.CONN_DOWN)
    check("o alerta fica registrado no histórico de avisos", any(r["kind"] == "conexao" for r in q(S, "SELECT kind FROM alerts")))
    print(f"\n{OK} ok, {FAIL} falha(s)"); sys.exit(1 if FAIL else 0)
asyncio.run(main())
