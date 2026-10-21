"""Cópia externa do backup (Supabase Storage): envio, retenção, erros e segurança."""
import asyncio, os, sys, tempfile, json
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
async def code(coro):
    try: await coro; return 200
    except Exception as e: return getattr(e, "status_code", 500)
async def main():
    S = harness.load_server(); S.PROVIDER = "qr"; U = harness.SUPA
    st = await S.offsite_status()
    check("sem configuração: desativado e o diagnóstico recomenda configurar", not st["enabled"] and await code(S.offsite_test()) == 400)
    d = await S.run_diagnostics(); o = next(c for c in d["checks"] if c["id"] == "offsite")
    check("diagnóstico: aviso de cópia externa não configurada", o["status"] == "aviso")
    os.environ["SUPABASE_URL"] = "https://wdfmfzlliudiohysczwb.supabase.co/"; os.environ["SUPABASE_SERVICE_KEY"] = "svc-key"
    st = await S.offsite_status()
    check("configurada: mostra o host e o bucket, nunca a chave", st["enabled"] and st["host"] == "wdfmfzlliudiohysczwb.supabase.co" and st["bucket"] == "sdr-backups" and "svc-key" not in json.dumps(st))
    t = await S.offsite_test()
    check("teste de conexão ok", t["ok"] and not t["warning"], t)
    U["public"] = True; t = await S.offsite_test(); U["public"] = False
    check("bucket público: avisa (backup tem dados pessoais)", t["ok"] and "PÚBLICO" in t["warning"], t)
    U["badkey"] = 1; t = await S.offsite_test(); U["badkey"] = 0
    check("chave errada: erro com orientação", not t["ok"] and "service_role" in t["error"], t)
    U["nobucket"] = 1; t = await S.offsite_test(); U["nobucket"] = 0
    check("bucket inexistente: erro com orientação", not t["ok"] and "bucket" in t["error"].lower(), t)
    # backup envia cópia
    r = await S.backups_create()
    check("backup manual envia o .zip ao bucket (conteúdo idêntico ao local)", r["name"] in U["objects"] and U["objects"][r["name"]] == (S.BACKUP_DIR / r["name"]).read_bytes())
    check("registra o último envio com sucesso", json.loads(S.get_setting("offsite_last"))["ok"])
    # retenção
    S.OFFSITE_KEEP = 3
    for i in range(5):
        n = f"sdr-20260101-00000{i}.zip"; (S.BACKUP_DIR / n).write_bytes(b"PK"); await S.offsite_upload(S.BACKUP_DIR / n)
    keep = sorted(U["objects"], reverse=True)
    check("retenção: só os 3 mais recentes ficam no bucket", len(keep) == 3, keep)
    # falha
    harness.HOOKS.clear(); os.environ["NOTIFY_WEBHOOK_URL"] = "https://hooks.example/x"
    U["fail"] = 1; await S.offsite_after(r["name"]); U["fail"] = 0
    last = json.loads(S.get_setting("offsite_last"))
    check("falha no Supabase: registra o erro e não derruba o backup local", not last["ok"] and (S.BACKUP_DIR / r["name"]).exists(), last)
    await asyncio.sleep(0.2)
    check("falha avisa por e-mail/webhook", any("backup" in json.dumps(x, ensure_ascii=False).lower() for x in harness.HOOKS), harness.HOOKS)
    # grande demais
    big = S.BACKUP_DIR / "sdr-20260102-000000.zip"; big.write_bytes(b"0")
    S.OFFSITE_MAX = 0; ok, msg = await S.offsite_upload(big); S.OFFSITE_MAX = 50_000_000
    check("arquivo acima do limite do plano gratuito: não tenta e explica", not ok and "50 MB" in msg)
    # automático
    S.set_setting("last_backup", "0"); S.BACKUP_AUTO = True
    n_before = len(U["objects"]); name = await S.maybe_backup()
    check("backup automático diário também envia a cópia externa", name and name in U["objects"], name)
    d = await S.run_diagnostics(); o = next(c for c in d["checks"] if c["id"] == "offsite")
    check("diagnóstico: ok depois de um envio", o["status"] == "ok", o)
    print(f"\n{OK} ok, {FAIL} falha(s)"); sys.exit(1 if FAIL else 0)
asyncio.run(main())
