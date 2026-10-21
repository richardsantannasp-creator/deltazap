"""Verificação em duas etapas (TOTP, RFC 6238) e perfil de supervisor (somente leitura)."""
import asyncio, os, sys, tempfile, time
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
def run(S, sql, *a):
    with S.conn() as c: c.execute(sql, a)
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0
def cur_code(S, secret, off=0):
    return S.totp_at(secret.replace(" ", ""), int(time.time() // 30) + off)
async def main():
    S = harness.load_server(); S.PROVIDER = "qr"; harness.GW["state"] = "open"
    # ---------- algoritmo: vetores do RFC 6238 (SHA-1, chave "12345678901234567890") ----------
    sec = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    check("RFC 6238: T=59 → 287082", S.totp_at(sec, 59 // 30) == "287082")
    check("RFC 6238: T=1111111109 → 081804", S.totp_at(sec, 1111111109 // 30) == "081804")
    check("RFC 6238: T=1234567890 → 005924", S.totp_at(sec, 1234567890 // 30) == "005924")
    check("tolera 1 janela de relógio", S.totp_check(sec, "287082", 0, now=59 + 30) == 1 and S.totp_check(sec, "287082", 0, now=59 + 90) == 0)
    check("código já usado não vale de novo", S.totp_check(sec, "287082", 1, now=59) == 0)
    check("código com letras ou tamanho errado é recusado", S.totp_check(sec, "28708", 0, now=59) == 0 and S.totp_check(sec, "abcdef", 0, now=59) == 0)
    # ---------- atendente ----------
    await S.agents_add(S.AgentIn(name="Ana", login="ana", password="senha-longa-1", max_chats=5))
    la = await S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1")); T = la["token"]
    check("começa sem 2FA", la["agent"]["twofa"] is False)
    s = await S.agent_2fa_setup(x_token=T)
    check("gera chave e endereço otpauth", len(s["secret"].replace(" ", "")) == 32 and s["uri"].startswith("otpauth://totp/") and "secret=" in s["uri"], s)
    check("antes de confirmar o login não pede código", "token" in await S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1")))
    check("confirmar com código errado: 400", await err(S.agent_2fa_enable(S.TwoFaIn(code="000000"), x_token=T)) == 400)
    r = await S.agent_2fa_enable(S.TwoFaIn(code=cur_code(S, s["secret"])), x_token=T)
    check("confirmar liga e devolve 8 códigos de recuperação", r["ok"] and len(r["recovery"]) == 8 and all(len(x) == 13 for x in r["recovery"]), r)
    check("os códigos de recuperação não ficam em texto", r["recovery"][0].replace("-", "") not in str(q(S, "SELECT totp_rec FROM agents")))
    check("já ligado: nova configuração é recusada", await err(S.agent_2fa_setup(x_token=T)) == 400)
    S.LOGIN_FAILS.clear()
    lg = await S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1"))
    check("com 2FA, senha certa sem código pede o código (sem token)", lg.get("need_code") is True and "token" not in lg, lg)
    check("senha errada continua 401", await err(S.agent_login(S.AgentLoginIn(login="ana", password="x", code="123456"))) == 401)
    check("código errado: 401", await err(S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1", code="111111"))) == 401)
    run(S, "UPDATE agents SET totp_last=0")
    ok = await S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1", code=cur_code(S, s["secret"])))
    check("código certo entra", "token" in ok and ok["agent"]["twofa"] is True)
    check("o mesmo código não entra de novo (replay)", await err(S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1", code=cur_code(S, s["secret"])))) == 401)
    rc = r["recovery"][0]
    ok2 = await S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1", code=rc))
    check("código de recuperação entra", "token" in ok2)
    check("código de recuperação só vale uma vez", await err(S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1", code=rc))) == 401)
    check("tentativas erradas contam no limite (429)", [await err(S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1", code="222222"))) for _ in range(6)][-1] == 429)
    S.LOGIN_FAILS.clear()
    check("desligar exige senha e código", await err(S.agent_2fa_disable(S.TwoFaIn(code="000000", password="senha-longa-1"), x_token=ok["token"])) == 400
          and await err(S.agent_2fa_disable(S.TwoFaIn(code=r["recovery"][1], password="errada"), x_token=ok["token"])) == 400)
    await S.agent_2fa_disable(S.TwoFaIn(code=r["recovery"][1], password="senha-longa-1"), x_token=ok["token"])
    check("desligado: login volta a ser só senha", "token" in await S.agent_login(S.AgentLoginIn(login="ana", password="senha-longa-1")) and not q(S, "SELECT totp_secret FROM agents")[0]["totp_secret"])
    # administrador libera quem perdeu o celular
    s = await S.agent_2fa_setup(x_token=T); run(S, "UPDATE agents SET totp_last=0")
    await S.agent_2fa_enable(S.TwoFaIn(code=cur_code(S, s["secret"])), x_token=T)
    aid = q(S, "SELECT id FROM agents")[0]["id"]
    check("administrador libera o acesso", (await S.agent_2fa_reset(aid))["ok"] and q(S, "SELECT totp_on FROM agents")[0]["totp_on"] == 0)
    check("liberar atendente inexistente: 404", await err(S.agent_2fa_reset(9999)) == 404)
    # ---------- gestor ----------
    await S.managers_add(S.ManagerIn(login="gil", name="Gil", password="senhaforte1"))
    lm = await S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1")); TM = lm["token"]
    check("gestor começa sem 2FA e com perfil gestor", lm["manager"]["twofa"] is False and lm["manager"]["role"] == "gestor")
    s = await S.gestor_2fa_setup(x_token=TM)
    r = await S.gestor_2fa_enable(S.TwoFaIn(code=cur_code(S, s["secret"])), x_token=TM)
    check("gestor liga o 2FA", r["ok"] and len(r["recovery"]) == 8)
    S.LOGIN_FAILS.clear()
    check("gestor: pede o código", (await S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1"))).get("need_code") is True)
    run(S, "UPDATE managers SET totp_last=0")
    check("gestor: código certo entra", "token" in await S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1", code=cur_code(S, s["secret"]))))
    check("gestor: código errado 401", await err(S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1", code="123123"))) == 401)
    mid = q(S, "SELECT id FROM managers WHERE login='gil'")[0]["id"]
    await S.manager_2fa_reset(mid)
    check("administrador libera o gestor", q(S, "SELECT totp_on FROM managers WHERE id=?", mid)[0]["totp_on"] == 0)
    check("a lista do administrador mostra o 2FA", all("twofa" in m for m in (await S.managers_list())["managers"]))
    # ---------- supervisor ----------
    S.upsert_lead("5521988880001", "Lead A", niche_id=1); S.upsert_lead("5521988880002", "Lead B", niche_id=1)
    S.add_msg("5521988880001", "lead", "olá"); S.add_msg("5521988880002", "lead", "oi")
    sp = await S.managers_add(S.ManagerIn(login="sup", name="Sônia Supervisora", password="senhaforte9", role="supervisor"))
    ls = await S.gestor_login(S.AgentLoginIn(login="sup", password="senhaforte9")); TS = ls["token"]
    check("supervisor entra com perfil supervisor", ls["manager"]["role"] == "supervisor")
    me = await S.gestor_me(x_token=TS)
    check("supervisor enxerga todos os números e atendentes", len(me["lines"]) >= 1 and len(me["agents"]) == 1, me)
    ls_ = await S.gestor_leads(x_token=TS)
    check("supervisor enxerga conversas de todas as equipes", {l["phone"] for l in ls_["leads"]} >= {"5521988880001", "5521988880002"}, ls_)
    check("supervisor lê as mensagens", len(await S.gestor_messages("5521988880001", x_token=TS)) == 1)
    check("supervisor vê o desempenho de todos", len((await S.gestor_metrics(x_token=TS))["agents"]) == 1)
    check("supervisor vê o histórico geral", "rows" in await S.gestor_audit(x_token=TS))
    for nome, coro in (("enviar mensagem", lambda: S.gestor_send("5521988880001", S.TextIn(text="oi"), x_token=TS)),
                       ("assumir conversa", lambda: S.gestor_takeover("5521988880001", S.TakeIn(human=True), x_token=TS)),
                       ("enviar à equipe", lambda: S.gestor_handoff("5521988880001", x_token=TS)),
                       ("etiquetar", lambda: S.gestor_lead_tags("5521988880001", S.LeadTagsIn(tags=[1]), x_token=TS)),
                       ("mover de etapa", lambda: S.gestor_lead_stage("5521988880001", S.StageIn(stage="qualificado"), x_token=TS)),
                       ("criar atendente", lambda: S.gestor_agent_add(S.AgentIn(login="x1", name="X", password="abcdef", max_chats=1), x_token=TS)),
                       ("conectar número", lambda: S.gestor_line_add(S.MgrLineIn(label="Novo"), x_token=TS))):
        check(f"supervisor não pode {nome} (403)", await err(coro()) == 403)
    check("nada mudou com as tentativas", S.get_lead("5521988880001")["stage"] != "qualificado" and not q(S, "SELECT 1 FROM lead_tags"))
    check("supervisor pode ligar o próprio 2FA", (await S.gestor_2fa_setup(x_token=TS))["secret"])
    TM = (await S.gestor_login(S.AgentLoginIn(login="gil", password="senhaforte1")))["token"]
    check("gestor comum não é barrado como supervisor (conversa alheia: 404, não 403)", await err(S.gestor_lead_stage("5521988880001", S.StageIn(stage="qualificado"), x_token=TM)) == 404)
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
