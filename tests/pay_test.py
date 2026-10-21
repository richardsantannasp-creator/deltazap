"""Testa o fechamento: ferramenta de link de pagamento (preço e desconto sob controle do sistema), Asaas/Stripe simulados, webhooks e pedidos."""
import asyncio, hashlib, hmac, json, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
os.environ["BACKUP_DIR"] = tempfile.mkdtemp(prefix="sdr-bk-")
import harness

OK = FAIL = 0
def check(nome, cond, extra=""):
    global OK, FAIL
    cond = bool(cond); OK += cond; FAIL += (not cond)
    print(("OK    " if cond else "FALHA ") + nome + ("" if cond else f"  -> {extra}"))
def q(S, sql, *a):
    with S.conn() as c: return [dict(r) for r in c.execute(sql, a)]
def run(S, sql, *a):
    with S.conn() as c: c.execute(sql, a)
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0
async def settle(): await asyncio.sleep(0.15)
class Req:
    def __init__(self, headers, body): self.headers, self._b = headers, body
    async def body(self): return self._b
    async def json(self): return json.loads(self._b or b"{}")

async def main():
    S = harness.load_server()
    await S.pacing_put({"min_delay": 1, "max_delay": 1, "batch_size": 50, "warmup": False, "daily_limit": 500, "reply_delay_min": 0, "reply_delay_max": 0,
                        "start_hour": 0, "end_hour": 24, "weekdays_only": False})
    PAY = lambda **k: S.PayIn(**{"provider": "fixo", **k})
    P = lambda **k: S.ProductIn(**{"niche_id": 1, "name": "Plano Ouro", "price": "1000,00", "max_discount_pct": 5, **k})
    N1 = S.get_niche(1)
    mk = lambda ph, **kw: (S.upsert_lead(ph, "Cliente " + ph[-2:], niche_id=1, origin="receptivo"), S.set_lead(ph, **kw))
    def tools(): return [t["name"] for t in S.tools_for(S.get_niche(1)) if t["name"] == "gerar_link_pagamento"]

    # ---------- quando a ferramenta existe ----------
    check("sem produto: sem ferramenta de pagamento", not tools())
    pid = (await S.product_add(P()))["id"]
    check("link fixo sem link cadastrado: sem ferramenta", not tools())
    await S.pay_put(PAY(provider="asaas"))
    check("Asaas sem chave: sem ferramenta (não oferece o que não consegue cumprir)", not tools())
    await S.pay_put(PAY(provider="asaas", asaas_key="ak_teste"))
    check("Asaas com chave e produto: ferramenta disponível", tools())
    check("esquema da ferramenta não tem campo de preço", "preco" not in json.dumps(S.payment_tools(N1)) and "valor" not in json.dumps(S.payment_tools(N1)))
    cfg = await S.pay_get()
    check("config nunca devolve a chave, só se existe; gera token de webhook", "ak_teste" not in json.dumps(cfg) and cfg["has_asaas"] and len(cfg["webhook_token"]) >= 20 and cfg["ready"], cfg)
    check("provedor inválido -> 400; retorno http -> 400; validade fora -> 400", await err(S.pay_put(PAY(provider="x"))) == 400 and await err(S.pay_put(PAY(success_url="http://a.com"))) == 400 and await err(S.pay_put(PAY(expire_hours=0))) == 400)

    # ---------- Asaas: preço e desconto vêm do cadastro ----------
    mk("5511900000011", stage="qualificando")
    ph = "5511900000011"
    S.PROVIDER_TEST = None
    r = await S.make_payment_link(ph, {"produto_id": pid, "quantidade": 2, "desconto_pct": 5, "preco": 1, "valor": 1})
    o = q(S, "SELECT * FROM orders ORDER BY id DESC LIMIT 1")[0]
    check("total = preço do cadastro × qtd × (1 − desconto), ignorando valor enviado pelo modelo", o["total_cents"] == 190000 and o["discount_pct"] == 5 and o["unit_cents"] == 100000, o)
    call = harness.PAYSIM["calls"][-1]
    check("Asaas: chamada ao sandbox com chave, valor e referência do pedido", "api-sandbox.asaas.com/v3/paymentLinks" in call["url"] and call["headers"]["access_token"] == "ak_teste"
          and call["json"]["value"] == 1900.0 and call["json"]["externalReference"] == f"sdr-{o['id']}" and call["json"]["billingType"] == "UNDEFINED", call)
    check("retorno entrega o link e o total para o agente colar", o["url"] in r and "R$ 1.900,00" in r and "5%" in r, r)
    lead = S.get_lead(ph)
    check("lead vira 'cotação enviada' e o pedido fica no CRM", lead["outcome"] == "cotacao_enviada" and "Plano Ouro x2" in json.loads(lead["bant"])["pedido"], dict(lead))
    n_calls = len(harness.PAYSIM["calls"])
    r2 = await S.make_payment_link(ph, {"produto_id": pid, "quantidade": 2, "desconto_pct": 5})
    check("pedido repetido devolve o mesmo link, sem nova cobrança", o["url"] in r2 and len(harness.PAYSIM["calls"]) == n_calls and len(q(S, "SELECT 1 FROM orders")) == 1)

    # ---------- limites rígidos ----------
    cnt = len(q(S, "SELECT 1 FROM orders"))
    for nome, inp in [("desconto acima do máximo", {"produto_id": pid, "quantidade": 1, "desconto_pct": 20}), ("desconto negativo", {"produto_id": pid, "quantidade": 1, "desconto_pct": -10}),
                      ("produto inexistente", {"produto_id": 9999, "quantidade": 1}), ("quantidade zero", {"produto_id": pid, "quantidade": 0}),
                      ("quantidade 100", {"produto_id": pid, "quantidade": 100}), ("texto no lugar de número", {"produto_id": "abc", "quantidade": 1}), ("sem parâmetros", {})]:
        res = await S.make_payment_link(ph, inp)
        check(f"recusa: {nome}", len(q(S, "SELECT 1 FROM orders")) == cnt and "Link gerado" not in res, res)
    res = await S.make_payment_link(ph, {"produto_id": pid, "quantidade": 1, "desconto_pct": 20})
    check("recusa de desconto orienta a oferecer o máximo ou chamar humano", "5%" in res and "transferir_para_humano" in res, res)
    n2 = (await S.niche_create(S.NicheIn(name="Outro", prompt="x", outbound_text="y SAIR")))["id"]
    other = (await S.product_add(S.ProductIn(niche_id=n2, name="De outro nicho", price="10")))["id"]
    check("produto de outro nicho é recusado", "não encontrado" in await S.make_payment_link(ph, {"produto_id": other, "quantidade": 1}))
    await S.product_edit(pid, P(active=False))
    check("produto inativo é recusado", "não encontrado" in await S.make_payment_link(ph, {"produto_id": pid, "quantidade": 1}))
    await S.product_edit(pid, P())

    # ---------- falha do provedor ----------
    harness.PAYSIM["fail"] = 1
    mk("5511900000012"); res = await S.make_payment_link("5511900000012", {"produto_id": pid, "quantidade": 1})
    harness.PAYSIM["fail"] = 0
    check("falha do provedor: mensagem segura, nenhum pedido órfão", "transferir_para_humano" in res and not q(S, "SELECT 1 FROM orders WHERE phone='5511900000012'"), res)
    check("a falha vai para o log do painel", q(S, "SELECT 1 FROM events WHERE kind='erro' AND text LIKE '%link de pagamento%'"))

    # ---------- lead de teste não cria cobrança real ----------
    S.upsert_lead("5511900000013", "Teste", niche_id=1, origin="receptivo"); S.set_lead("5511900000013", test=1)
    n_calls = len(harness.PAYSIM["calls"])
    res = await S.make_payment_link("5511900000013", {"produto_id": pid, "quantidade": 1})
    check("lead de teste: link falso, sem chamar o provedor, pedido marcado como teste", "pagamento-teste.invalid" in res and len(harness.PAYSIM["calls"]) == n_calls
          and q(S, "SELECT test FROM orders WHERE phone='5511900000013'")[0]["test"] == 1)

    # ---------- webhook do Asaas ----------
    tok = (await S.pay_get())["webhook_token"]
    ev = lambda **p: {"event": "PAYMENT_RECEIVED", "payment": {"id": "pay_1", "paymentLink": o["ext_id"], "value": 1900.0, **p}}
    R = lambda body, h: Req(h, json.dumps(body).encode())
    check("webhook sem token / token errado -> 401", await err(S.pay_webhook_asaas(R(ev(), {}))) == 401 and await err(S.pay_webhook_asaas(R(ev(), {"asaas-access-token": "x"}))) == 401)
    check("webhook com JSON inválido -> 400", await err(S.pay_webhook_asaas(Req({"asaas-access-token": tok}, b"{nao")) ) == 400)
    r = await S.pay_webhook_asaas(R({"event": "PAYMENT_CREATED", "payment": {}}, {"asaas-access-token": tok}))
    check("evento que não é pagamento é ignorado", r.get("ignorado") == "PAYMENT_CREATED")
    r = await S.pay_webhook_asaas(R(ev(value=1800.0), {"asaas-access-token": tok}))
    check("valor pago menor que o pedido NÃO fecha a venda", r.get("divergente") and q(S, "SELECT status FROM orders WHERE id=?", o["id"])[0]["status"] == "link")
    harness.SENT.clear()
    r = await S.pay_webhook_asaas(R(ev(), {"asaas-access-token": tok})); await settle()
    lead = S.get_lead(ph)
    check("pagamento confirmado: pedido pago, lead ganho, venda no CRM", q(S, "SELECT status,paid_via FROM orders WHERE id=?", o["id"])[0] == {"status": "pago", "paid_via": "asaas"}
          and lead["outcome"] == "ganho" and "R$ 1.900,00" in json.loads(lead["bant"])["venda"], (r, dict(lead)))
    check("equipe é avisada da venda", q(S, "SELECT 1 FROM alerts WHERE kind='venda' AND phone=?", ph))
    check("cliente recebe a confirmação no WhatsApp", any(m["to"] == ph and "Pagamento confirmado" in m["text"] for m in harness.SENT), harness.SENT)
    harness.SENT.clear(); n_al = len(q(S, "SELECT 1 FROM alerts WHERE kind='venda'"))
    await S.pay_webhook_asaas(R(ev(), {"asaas-access-token": tok})); await settle()
    check("mesmo aviso de novo não repete aviso nem mensagem (idempotente)", not harness.SENT and len(q(S, "SELECT 1 FROM alerts WHERE kind='venda'")) == n_al)
    r = await S.pay_webhook_asaas(R({"event": "PAYMENT_CONFIRMED", "payment": {"id": "x", "paymentLink": "inexistente", "value": 5}}, {"asaas-access-token": tok}))
    check("pagamento sem pedido correspondente: 200 e registro, sem efeito", r.get("pedido") is None)
    mk("5511900000014"); await S.make_payment_link("5511900000014", {"produto_id": pid, "quantidade": 1}); o2 = q(S, "SELECT * FROM orders WHERE phone='5511900000014'")[0]
    r = await S.pay_webhook_asaas(R({"event": "PAYMENT_CONFIRMED", "payment": {"id": "p9", "externalReference": f"sdr-{o2['id']}", "value": 1000.0}}, {"asaas-access-token": tok}))
    check("localiza o pedido pela referência externa se faltar o id do link", r.get("pedido") == o2["id"] and q(S, "SELECT status FROM orders WHERE id=?", o2["id"])[0]["status"] == "pago")

    # ---------- Stripe ----------
    await S.pay_put(PAY(provider="stripe", stripe_key="sk_teste", stripe_whsec="whsec_abc", success_url="https://loja.exemplo/obrigado"))
    mk("5511900000015"); res = await S.make_payment_link("5511900000015", {"produto_id": pid, "quantidade": 3, "desconto_pct": 0})
    o3 = q(S, "SELECT * FROM orders WHERE phone='5511900000015'")[0]; call = harness.PAYSIM["calls"][-1]
    d = call["data"]
    check("Stripe: sessão com valor em centavos, referência e retorno", "api.stripe.com/v1/checkout/sessions" in call["url"] and call["headers"]["Authorization"] == "Bearer sk_teste"
          and d["line_items[0][price_data][unit_amount]"] == 300000 and d["line_items[0][price_data][currency]"] == "brl" and d["client_reference_id"] == f"sdr-{o3['id']}"
          and d["success_url"] == "https://loja.exemplo/obrigado" and d["mode"] == "payment" and int(d["expires_at"]) > time.time(), d)
    body = lambda **kw: json.dumps({"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {"id": o3["ext_id"], "client_reference_id": f"sdr-{o3['id']}", "payment_status": "paid", "amount_total": 300000, **kw}}}).encode()
    sign = lambda raw, t=None, key="whsec_abc": f"t={t or int(time.time())},v1=" + hmac.new(key.encode(), f"{t or int(time.time())}".encode() + b"." + raw, hashlib.sha256).hexdigest()
    b = body()
    check("Stripe: assinatura errada / adulterada / antiga -> 401",
          await err(S.pay_webhook_stripe(Req({"Stripe-Signature": sign(b, key="outra")}, b))) == 401 and await err(S.pay_webhook_stripe(Req({"Stripe-Signature": sign(b)}, b + b" "))) == 401
          and await err(S.pay_webhook_stripe(Req({"Stripe-Signature": sign(b, t=int(time.time()) - 4000)}, b))) == 401 and await err(S.pay_webhook_stripe(Req({}, b))) == 401)
    bu = body(payment_status="unpaid")
    r = await S.pay_webhook_stripe(Req({"Stripe-Signature": sign(bu)}, bu))
    check("sessão ainda não paga é ignorada", r.get("ignorado") and q(S, "SELECT status FROM orders WHERE id=?", o3["id"])[0]["status"] == "link")
    bl = body(amount_total=1000)
    r = await S.pay_webhook_stripe(Req({"Stripe-Signature": sign(bl)}, bl))
    check("Stripe: valor menor que o pedido não fecha a venda", r.get("divergente") and q(S, "SELECT status FROM orders WHERE id=?", o3["id"])[0]["status"] == "link")
    r = await S.pay_webhook_stripe(Req({"Stripe-Signature": sign(b)}, b)); await settle()
    check("Stripe: pagamento confirma o pedido e fecha o lead", q(S, "SELECT status,paid_via FROM orders WHERE id=?", o3["id"])[0] == {"status": "pago", "paid_via": "stripe"} and S.get_lead("5511900000015")["outcome"] == "ganho", r)
    other_evt = json.dumps({"type": "charge.refunded", "data": {"object": {}}}).encode()
    check("outros eventos do Stripe são ignorados", (await S.pay_webhook_stripe(Req({"Stripe-Signature": sign(other_evt)}, other_evt))).get("ignorado") == "charge.refunded")
    check("sem segredo configurado nenhum evento do Stripe passa", (await S.pay_put(PAY(provider="stripe", stripe_key="sk_teste"))) is not None and True)
    run(S, "UPDATE settings SET v=json_remove(v,'$.stripe_whsec') WHERE k='pay'")
    check("Stripe sem whsec -> 401", await err(S.pay_webhook_stripe(Req({"Stripe-Signature": sign(b)}, b))) == 401)

    # ---------- link fixo + baixa manual ----------
    await S.pay_put(PAY(provider="fixo"))
    pf = (await S.product_add(P(name="Kit Fixo", price="50", pay_url="https://pagar.exemplo/kit", max_discount_pct=10)))["id"]
    check("link fixo: ferramenta disponível", tools())
    mk("5511900000016")
    res = await S.make_payment_link("5511900000016", {"produto_id": pf, "quantidade": 1})
    check("link fixo devolve o link cadastrado e total do cadastro", "https://pagar.exemplo/kit" in res and "R$ 50,00" in res, res)
    res = await S.make_payment_link("5511900000016", {"produto_id": pf, "quantidade": 1, "desconto_pct": 5})
    check("link fixo não aceita desconto (o link tem valor fixo)", "Link gerado" not in res and "sem desconto" in res, res)
    res = await S.make_payment_link("5511900000016", {"produto_id": pid, "quantidade": 1})
    check("link fixo: produto sem link cadastrado é recusado", "não tem link" in res, res)
    of = q(S, "SELECT * FROM orders WHERE phone='5511900000016'")[0]
    await S.order_paid(of["id"])
    check("baixa manual fecha a venda (paid_via=manual)", q(S, "SELECT status,paid_via FROM orders WHERE id=?", of["id"])[0] == {"status": "pago", "paid_via": "manual"} and S.get_lead("5511900000016")["outcome"] == "ganho")
    check("baixa de pedido inexistente -> 404; cancelar pedido pago -> 400", await err(S.order_paid(9999)) == 404 and await err(S.order_cancel(of["id"])) == 400)
    mk("5511900000017"); await S.make_payment_link("5511900000017", {"produto_id": pf, "quantidade": 2}); oc = q(S, "SELECT id FROM orders WHERE phone='5511900000017'")[0]
    await S.order_cancel(oc["id"])
    check("cancelar pedido com link pendente", q(S, "SELECT status FROM orders WHERE id=?", oc["id"])[0]["status"] == "cancelado")

    # ---------- lista, totais e conexão ----------
    lst = await S.orders_list(30)
    check("lista de pedidos: totais e conversão, sem pedidos de teste", lst["total"] == len(lst["orders"]) and all(not x["test"] for x in lst["orders"]) and lst["paid"] >= 3 and lst["revenue_cents"] >= 190000 + 300000 and lst["conv_pct"] > 0, {k: v for k, v in lst.items() if k != "orders"})
    check("lista de teste inclui os pedidos de teste quando pedido", any(x["test"] for x in (await S.orders_list(30, 1))["orders"]))
    await S.pay_put(PAY(provider="asaas", asaas_key="ak_teste"))
    check("testar conexão: chave válida", (await S.pay_test())["ok"])
    harness.PAYSIM["badkey"] = 1
    t = await S.pay_test(); harness.PAYSIM["badkey"] = 0
    check("testar conexão: chave recusada explica", not t["ok"] and "recusada" in t["detail"], t)
    old_tok = (await S.pay_get())["webhook_token"]
    new = await S.pay_put(PAY(provider="asaas", new_token=True))
    check("trocar o token do webhook invalida o antigo", new["webhook_token"] != old_tok and await err(S.pay_webhook_asaas(R(ev(), {"asaas-access-token": old_tok}))) == 401)
    check("salvar sem chave nova mantém a chave", (await S.pay_get())["has_asaas"])

    # ---------- fluxo completo pelo agente (Claude simulado pede a ferramenta) ----------
    await S.pay_put(PAY(provider="asaas", asaas_key="ak_teste"))
    harness.PAYSIM["tool_input"] = {"produto_id": pid, "quantidade": 1}
    harness.CALLS.clear()
    await S.handle_incoming("5511977770099", "Dora", "oi", None, False)
    await S.handle_incoming("5511977770099", "Dora", "quero fechar o plano ouro", None, False)
    check("o agente recebe a ferramenta de pagamento na chamada", any(c["kind"] == "agente" and c["tools"] == 5 for c in harness.CALLS), [c["tools"] for c in harness.CALLS])
    check("o agente gerou o pedido pela ferramenta (preço do cadastro)", q(S, "SELECT total_cents FROM orders WHERE phone='5511977770099'") == [{"total_cents": 100000}])

    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
