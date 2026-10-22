"""Plano de aquecimento de 14 dias por número, com freio automático e plano editável."""
import asyncio, os, sys, tempfile, time
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness
OK = FAIL = 0
def check(n, c, x=""):
    global OK, FAIL
    c = bool(c); OK += c; FAIL += (not c)
    print(("OK    " if c else "FALHA ") + n + ("" if c else f"  -> {str(x)[:300]}"))
def run(S, sql, *a):
    with S.conn() as c: c.execute(sql, a)
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0
async def main():
    S = harness.load_server(); S.PROVIDER = "qr"
    await S.pacing_put({"daily_limit": 200, "warmup": True})
    cfg = S.get_pacing()
    day = lambda n: (date.today() - timedelta(days=n)).isoformat()
    run(S, "UPDATE lines SET first_send_day=? WHERE id='main'", day(0))
    check("dia 1: 10 envios", S.allowed_today(cfg, "main") == 10, S.allowed_today(cfg, "main"))
    for d, v in ((2, 20), (6, 50), (13, 120)):
        run(S, "UPDATE lines SET first_send_day=? WHERE id='main'", day(d))
        check(f"dia {d + 1}: {v} envios", S.allowed_today(cfg, "main") == v, S.allowed_today(cfg, "main"))
    run(S, "UPDATE lines SET first_send_day=? WHERE id='main'", day(30))
    check("depois de 14 dias vale o limite diário", S.allowed_today(cfg, "main") == 200)
    await S.pacing_put({"daily_limit": 40, "warmup": True})
    run(S, "UPDATE lines SET first_send_day=? WHERE id='main'", day(13))
    check("o limite diário continua mandando mais que o plano", S.allowed_today(S.get_pacing(), "main") == 40)
    await S.pacing_put({"daily_limit": 200, "warmup": False})
    run(S, "UPDATE lines SET first_send_day=? WHERE id='main'", day(0))
    check("aquecimento desligado: só o limite diário", S.allowed_today(S.get_pacing(), "main") == 200)
    await S.pacing_put({"daily_limit": 200, "warmup": True})
    # ---------- freio ----------
    run(S, "UPDATE lines SET first_send_day=? WHERE id='main'", day(5))
    check("sem histórico: sem freio", not S.line_health("main")["hold"] and S.allowed_today(S.get_pacing(), "main") == 40)
    now = time.time()
    for i in range(20):
        run(S, "INSERT INTO outbox(phone,niche_id,status,sent_at,line,created) VALUES(?,?,?,?,?,?)", f"55219000000{i:02d}", 1, "sent", now - 3600, "main", now - 7200)
    h = S.line_health("main")
    check("20 envios sem nenhuma resposta: segura", h["hold"] and h["sent"] == 20 and h["reply_pct"] == 0, h)
    check("segurando: o limite cai à metade (mínimo 10)", S.allowed_today(S.get_pacing(), "main") == 20, S.allowed_today(S.get_pacing(), "main"))
    for i in range(3):
        S.upsert_lead(f"55219000000{i:02d}", "L", niche_id=1); S.add_msg(f"55219000000{i:02d}", "lead", "oi")
    check("com respostas suficientes (15%) o freio sai", not S.line_health("main")["hold"] and S.allowed_today(S.get_pacing(), "main") == 40)
    for i in range(3, 20):
        S.upsert_lead(f"55219000000{i:02d}", "L", niche_id=1)
    for i in range(3, 8): S.set_lead(f"55219000000{i:02d}", stage="descartado")
    for i in range(3, 10): S.add_msg(f"55219000000{i:02d}", "lead", "oi")
    h = S.line_health("main")
    check("muitas saídas (4%+) também seguram", h["optout_pct"] >= 4 and h["hold"], h)
    run(S, "DELETE FROM outbox")
    check("freio é por número (outro número não é afetado)", not S.line_health("outro")["hold"])
    ls = [l for l in S.line_summary() if l["id"] == "main"][0]
    check("o painel recebe o dia do aquecimento", ls["warm_day"] == 6 and ls["warm_hold"] is False, ls)
    # ---------- plano editável ----------
    g = await S.warmup_get()
    check("lista o plano padrão e os números", len(g["plan"]) == 14 and g["plan"][0] == 10 and g["lines"][0]["id"] == "main")
    bad = [("curto", [10, 20]), ("texto", ["a"] * 14), ("zero", [0] + [10] * 13), ("alto", [10] * 13 + [999]),
           ("decrescente", [10, 20, 30, 25] + [40] * 10), ("agressivo no 1º dia", [50] * 14), ("agressivo no 7º dia", [10] * 6 + [150] * 8)]
    for nome, pl in bad:
        check(f"plano inválido recusado: {nome}", await err(S.warmup_put({"plan": pl})) == 400)
    ok = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
    await S.warmup_put({"plan": ok})
    run(S, "UPDATE lines SET first_send_day=? WHERE id='main'", day(0))
    check("plano personalizado vale", S.warmup_plan() == ok and S.allowed_today(S.get_pacing(), "main") == 5)
    await S.warmup_put({"plan": "default"})
    check("voltar ao padrão", S.warmup_plan()[0] == 10)
    m = await S.pacing_get()
    check("a configuração de ritmo traz o plano", m["warmup_plan"][0] == 10 and m["warmup_start"] == 10)
    check("o histórico de ações tem rótulo", S.audit_label("PUT", "/api/warmup")[0].startswith("Alterou o plano"))
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
