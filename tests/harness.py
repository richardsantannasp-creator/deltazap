"""Ambiente de teste SEM rede: carrega o server.py REAL com substitutos leves de fastapi, pydantic, httpx e anthropic
(WhatsApp, gateway, Claude e Whisper são simulados) e expõe as rotas por HTTP para testar o painel num navegador.
Uso: python tests/harness.py 8765      (variáveis: veja DEFAULT_ENV)"""
import asyncio, base64, inspect, json, mimetypes, os, re, sys, tempfile, time, types
from types import SimpleNamespace as NS
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="sdr-test-")
DEFAULT_ENV = {"DB_PATH": f"{TMP}/t.db", "UPLOADS_DIR": f"{TMP}/up", "DASH_TOKEN": "testtoken", "PROVIDER": "qr",
               "GATEWAY_SECRET": "seg", "ANTHROPIC_API_KEY": "x", "STT_PROVIDER": "openai", "OPENAI_API_KEY": "k"}

# ---------- estado simulado ----------
SENT, CALLS, GW_LOG, HOOKS, MAIL, CRM = [], [], [], [], [], []
PUSHLOG = []   # avisos push enviados (endereços "push.test")
def _default_lead(system, msgs):
    n = sum(1 for m in msgs if m["role"] == "assistant")
    if "escreva apenas: SAIR" in system: return "oi, o que vocês vendem?" if n == 0 else "SAIR"
    if "pergunte se está falando com um robô" in system: return "Oi, você é um robô?" if n == 0 else "ok, quanto custa o plano ouro?"
    return f"quero saber mais ({n})"
EVALSIM = {"lead": _default_lead, "judge_raw": "", "judge_fail": 0}
AGENT_HOOK = {"fn": None}
MEMSIM = {"fn": lambda user: "- Quer plano para 2 pessoas em Campinas\n- Orçamento até R$ 900\n- Combinou retorno na sexta"}
PDFSIM = {"fn": lambda k: "# Tabela\n| Plano | Valor |\n|---|---|\n| Ouro | R$ 1.234,56 |"}
SUPA = {"objects": {}, "calls": [], "fail": 0, "badkey": 0, "nobucket": 0, "public": False}
GCAL = {"calls": [], "busy": [], "events": {}, "n": 0, "pub": None, "token_fail": 0, "forbidden": 0, "tokens": 0, "fail_create": 0}
MEDIA = {"sent": [], "graph": [], "window": 0, "fail": 0}
WASIM = {"phone": {"display_phone_number": "+55 21 99999-0000", "verified_name": "Minha Corretora", "quality_rating": "GREEN", "name_status": "APPROVED", "messaging_limit_tier": "TIER_250"}, "templates": [{"name": "planos_de_saude_abertura", "status": "APPROVED"}], "tpl_error": 0, "phone_status": 200}
PAYSIM = {"calls": [], "fail": 0, "badkey": 0, "n": 0}
PD = {"persons": [], "deals": {}, "notes": [], "acts": [], "fail": 0, "calls": []}
HS = {"contacts": [], "deals": {}, "notes": [], "assoc": [], "fail": 0, "calls": []}
USAGE = {"in": 1000, "out": 200, "cr": 3000, "cw": 0}
GWL = {}   # outras linhas (números) do gateway simulado: id -> {state, me}
GW = {"state": "open", "qr": "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/%3E", "me": "5521999990000"}

# ---------- substitutos ----------
class HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        self.status_code, self.detail = status_code, detail
class _Header:
    def __init__(self, default=None): self.default = default
class _Dep:
    def __init__(self, f): self.f = f
class FakeRequest:
    def __init__(self, headers, body, query): self.headers, self._b, self.query_params = headers, body, query
    async def body(self): return self._b
    async def json(self): return json.loads(self._b or b"{}")
class BackgroundTasks:
    def __init__(self): self.tasks = []
    def add_task(self, f, *a, **k): self.tasks.append((f, a, k))
class FileResponse:
    def __init__(self, path, **kw): self.path = str(path)
class Response:
    def __init__(self, content=b"", media_type="text/plain", headers=None, **kw):
        self.content, self.media_type, self.headers = content, media_type, headers or {}
class HTMLResponse: pass
ROUTES, STARTUP = [], []
MIDDLEWARE = []
class FastAPI:
    def __init__(self, **k): pass
    def _reg(self, method):
        def deco(path, **kw):
            def wrap(fn): ROUTES.append((method, path, fn, kw)); return fn
            return wrap
        return deco
    def __getattr__(self, name):
        if name in ("get", "post", "put", "delete"): return self._reg(name.upper())
        raise AttributeError(name)
    def middleware(self, kind):
        def wrap(fn): MIDDLEWARE.append(fn); return fn
        return wrap
    def on_event(self, ev):
        def wrap(fn): STARTUP.append(fn); return fn
        return wrap
class BaseModel:
    def __init__(self, **kw):
        names = {}
        for c in reversed(type(self).__mro__):
            names.update(getattr(c, "__annotations__", {}))
        for n in names:
            if n in kw: setattr(self, n, kw[n])
            elif not hasattr(type(self), n): raise ValueError(f"campo obrigatório ausente: {n}")
PHOTO = {"have": set(), "calls": [], "png": bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")}
def json_params(k): return dict(k.get("params") or {})
class FakeResp:
    def __init__(self, status=200, data=None, content=b"", headers=None):
        self.status_code, self._d, self.content, self.headers = status, data if data is not None else {}, content, headers or {}
        self.text = json.dumps(self._d)
    def json(self): return self._d
class FakeClient:
    def __init__(self, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def get(self, url, headers=None, **k): return await self.request("GET", url, headers=headers, **k)
    async def post(self, url, headers=None, json=None, **k): return await self.request("POST", url, headers=headers, json=json, **k)
    async def delete(self, url, headers=None, **k): return await self.request("DELETE", url, headers=headers, **k)
    async def request(self, method, url, headers=None, json=None, **k):
        real = os.environ.get("REAL_GATEWAY")     # com REAL_GATEWAY=http://..., as chamadas ao gateway vão para o conector Node de verdade
        if real and url.startswith(real):
            import urllib.request, urllib.error
            def go():
                rq = urllib.request.Request(url, method=method, headers={**(headers or {}), "Content-Type": "application/json"},
                                            data=__import__("json").dumps(json).encode() if json is not None else None)
                try:
                    with urllib.request.urlopen(rq, timeout=60) as r: return r.status, r.read()
                except urllib.error.HTTPError as e: return e.code, e.read()
            st, raw = await asyncio.to_thread(go)
            try: data = __import__("json").loads(raw or b"{}")
            except ValueError: data = {}
            return FakeResp(st, data)
        if "push.test" in url:
            PUSHLOG.append({"url": url, "headers": headers or {}, "body": k.get("content")})
            return FakeResp(410 if "gone" in url else 201, {})
        if "supabase.co" in url:
            p_ = urlparse(url).path; SUPA["calls"].append((method, p_))
            if SUPA["badkey"] or (headers or {}).get("apikey") != "svc-key": return FakeResp(401, {"message": "Invalid API key"})
            if SUPA["nobucket"]: return FakeResp(404, {"message": "Bucket not found"})
            if SUPA["fail"]: return FakeResp(500, {"message": "boom"})
            if p_.startswith("/storage/v1/object/list/"):
                return FakeResp(200, [{"name": n} for n in sorted(SUPA["objects"], reverse=True)])
            if p_.startswith("/storage/v1/bucket/"): return FakeResp(200, {"public": SUPA["public"]})
            if method == "POST": SUPA["objects"][p_.rsplit("/", 1)[1]] = k.get("content"); return FakeResp(200, {"Key": p_})
            if method == "DELETE":
                for n in json["prefixes"]: SUPA["objects"].pop(n, None)
                return FakeResp(200, [])
        if "googleapis.com" in url:
            return _fake_google(method, url, headers or {}, json, k.get("data"))
        if "graph.facebook.com" in url:
            MEDIA["graph"].append({"url": url, "json": json, "files": k.get("files"), "data": k.get("data")})
            if method == "GET" and "message_templates" in url: return FakeResp(200, {"data": WASIM["templates"]})
            if method == "GET": return FakeResp(WASIM["phone_status"], WASIM["phone"] if WASIM["phone_status"] < 300 else {"error": {"message": "Invalid OAuth"}})
            if WASIM["tpl_error"] and json and json.get("type") == "template": return FakeResp(400, {"error": {"code": 132001, "message": "Template name does not exist in the translation"}})
            if url.endswith("/media"): return FakeResp(500, {}) if MEDIA["fail"] else FakeResp(200, {"id": "media_1"})
            if MEDIA["window"]: return FakeResp(400, {"error": {"code": 131047, "message": "Re-engagement message"}})
            return FakeResp(200, {"messages": [{"id": "wamid.x"}]})
        if "asaas.com" in url or "api.stripe.com" in url:
            PAYSIM["calls"].append({"method": method, "url": url, "headers": headers, "json": json, "data": k.get("data")})
            if PAYSIM["badkey"]: return FakeResp(401, {"errors": [{"description": "chave inválida"}]})
            if PAYSIM["fail"]: return FakeResp(500, {})
            if method == "GET": return FakeResp(200, {})
            PAYSIM["n"] += 1; n = PAYSIM["n"]
            if "asaas.com" in url: return FakeResp(200, {"id": f"pl_{n}", "url": f"https://sandbox.asaas.com/l/pl_{n}"})
            return FakeResp(200, {"id": f"cs_test_{n}", "url": f"https://checkout.stripe.com/c/pay/cs_test_{n}"})
        if "pipedrive.com/api/v1" in url:
            return _fake_pipedrive(method, url, k.get("params") or {}, json)
        if "api.hubapi.com" in url:
            return _fake_hubspot(method, url, headers or {}, k.get("params") or {}, json)
        if "crm.example" in url:
            CRM.append({"url": url, "headers": headers, "body": k.get("content")})
            return FakeResp(500 if "falha" in url else 200, {})
        if "hooks.example" in url:
            HOOKS.append(json); return FakeResp(500 if "falha" in url else 200, {})
        if "api.openai.com" in url:
            GW_LOG.append(("stt", k.get("data"))); return FakeResp(200, {"text": "oi, recebi uma multa e o prazo vence dia 16"})
        path = urlparse(url).path
        GW_LOG.append((path, json))
        if (headers or {}).get("x-secret") != DEFAULT_ENV["GATEWAY_SECRET"]: return FakeResp(403, {"error": "forbidden"})
        ln = (headers or {}).get("x-line", "main")
        if path == "/lines":
            return FakeResp(200, [{"id": "main", "state": GW["state"], "me": GW["me"] if GW["state"] == "open" else None}] +
                                 [{"id": k, "state": v["state"], "me": v["me"] if v["state"] == "open" else None} for k, v in GWL.items()])
        if path == "/line/add":
            if json["id"] != "main": GWL.setdefault(json["id"], {"state": "qr", "me": "5521999990" + str(len(GWL) + 1).zfill(3)})
            return FakeResp(200, {"ok": True})
        if path == "/line/remove": GWL.pop(json["id"], None); return FakeResp(200, {"ok": True})
        G = GW if ln == "main" else GWL.get(ln)
        if G is None: return FakeResp(404, {"error": "linha desconhecida"})
        if path == "/status": return FakeResp(200, {"state": G["state"], "qr": GW["qr"] if G["state"] == "qr" else None, "me": G["me"] if G["state"] == "open" else None, "line": ln})
        if path == "/photo":
            PHOTO["calls"].append((json_params(k), ln))
            if G["state"] != "open": return FakeResp(503, {"error": "WhatsApp não conectado"})
            who = (k.get("params") or {}).get("to", "")
            if who in PHOTO["have"] or who == "me": return FakeResp(200, content=PHOTO["png"], headers={"content-type": "image/png"})
            return FakeResp(404, {"error": "sem foto"})
        if path == "/send":
            if G["state"] != "open": return FakeResp(503, {"error": "WhatsApp não conectado"})
            if json["to"].endswith("404"): return FakeResp(404, {"error": "número sem WhatsApp"})
            SENT.append({"to": json["to"], "text": json["text"], "typing_ms": json.get("typing_ms", 0), "line": ln}); return FakeResp(200, {"ok": True})
        if path == "/send-media":
            if G["state"] != "open": return FakeResp(503, {"error": "WhatsApp não conectado"})
            if json["to"].endswith("404"): return FakeResp(404, {"error": "número sem WhatsApp"})
            if MEDIA["fail"]: return FakeResp(500, {"error": "boom"})
            MEDIA["sent"].append({k_: json[k_] for k_ in ("to", "kind", "mime", "filename", "caption")} | {"bytes": len(json["data"]), "line": ln}); return FakeResp(200, {"ok": True})
        if path == "/pair":
            if len(json["phone"]) < 10: return FakeResp(400, {"error": "Informe o número com DDI e DDD"})
            if G["state"] not in ("qr", "connecting"): return FakeResp(503, {"error": "Aguarde o gateway iniciar"})
            return FakeResp(200, {"code": "ABCD-EFGH"})
        if path == "/logout": G["state"] = "qr"; return FakeResp(200, {"ok": True})
        return FakeResp(404, {})
def _fake_google(method, url, headers, body, data):
    import base64 as b64, json as J, time as T
    path = urlparse(url).path
    GCAL["calls"].append((method, path, body or data))
    if "oauth2.googleapis.com" in url:
        if GCAL["token_fail"]: return FakeResp(400, {"error": "invalid_grant", "error_description": "Invalid JWT Signature."})
        jwt = (data or {}).get("assertion", "")
        try:
            hd, cl, sg = jwt.split(".")
            pad = lambda x: x + "=" * (-len(x) % 4)
            head, claim = J.loads(b64.urlsafe_b64decode(pad(hd))), J.loads(b64.urlsafe_b64decode(pad(cl)))
            if GCAL["pub"] is not None:
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import padding
                GCAL["pub"].verify(b64.urlsafe_b64decode(pad(sg)), f"{hd}.{cl}".encode(), padding.PKCS1v15(), hashes.SHA256())
            assert head["alg"] == "RS256" and claim["scope"].endswith("/auth/calendar") and claim["aud"] == "https://oauth2.googleapis.com/token" and claim["exp"] > claim["iat"]
        except Exception as e:
            return FakeResp(400, {"error": "invalid_grant", "error_description": "assinatura inválida: " + str(e)[:60]})
        GCAL["tokens"] += 1
        return FakeResp(200, {"access_token": f"tok{GCAL['tokens']}", "expires_in": 3600})
    if headers.get("Authorization") != f"Bearer tok{GCAL['tokens']}": return FakeResp(401, {"error": {"message": "invalid"}})
    if GCAL["forbidden"]: return FakeResp(404, {"error": {"message": "Not Found"}})
    if path.endswith("/freeBusy"):
        cid = body["items"][0]["id"]
        from datetime import datetime as DT
        t0, t1 = DT.fromisoformat(body["timeMin"]), DT.fromisoformat(body["timeMax"])
        inr = [b for b in GCAL["busy"] if DT.fromisoformat(b[0]) < t1 and DT.fromisoformat(b[1]) > t0]       # o Google só devolve o que cruza o período pedido
        return FakeResp(200, {"calendars": {cid: {"busy": [{"start": b[0], "end": b[1]} for b in inr]}}})
    GCAL.setdefault("log", []).append((method, path))
    if "/events" in path:
        if method == "POST":
            if GCAL["fail_create"]: return FakeResp(500, {"error": {"message": "boom"}})
            GCAL["n"] += 1; eid = f"ev{GCAL['n']}"; GCAL["events"][eid] = body; return FakeResp(200, {"id": eid, "htmlLink": "https://calendar.google.com/x"})
        if method == "DELETE":
            GCAL["events"].pop(path.rsplit("/", 1)[1], None); return FakeResp(204, content=b"")
    if "/calendars/" in path and method == "GET": return FakeResp(200, {"summary": "Comercial"})
    return FakeResp(404, {})
def _fake_pipedrive(method, url, params, body):
    path = urlparse(url).path.split("/api/v1", 1)[1]
    PD["calls"].append((method, path, params.get("api_token"), body))
    if params.get("api_token") != "pdtok": return FakeResp(401, {"success": False, "error": "unauthorized"})
    if PD["fail"] > 0:
        PD["fail"] -= 1; return FakeResp(500, {"success": False, "error": "boom"})
    if path == "/users/me": return FakeResp(200, {"success": True, "data": {"name": "Vendedor Teste"}})
    if path == "/persons/search":
        items = [{"item": {"id": p["id"]}} for p in PD["persons"] if any(ph["value"].lstrip("+") == params.get("term") or ph["value"] == "+" + params.get("term", "") for ph in p["phone"])]
        return FakeResp(200, {"success": True, "data": {"items": items}})
    if path == "/persons" and method == "POST":
        pid = 100 + len(PD["persons"]); PD["persons"].append({"id": pid, **body}); return FakeResp(201, {"success": True, "data": {"id": pid}})
    if path == "/deals" and method == "POST":
        did = 500 + len(PD["deals"]); PD["deals"][did] = {"id": did, "status": "open", **body}; return FakeResp(201, {"success": True, "data": {"id": did}})
    m = re.match(r"/deals/(\d+)$", path)
    if m and method == "PUT": PD["deals"][int(m[1])].update(body); return FakeResp(200, {"success": True, "data": {"id": int(m[1])}})
    if path == "/notes": PD["notes"].append(body); return FakeResp(201, {"success": True, "data": {"id": len(PD["notes"])}})
    if path == "/activities": PD["acts"].append(body); return FakeResp(201, {"success": True, "data": {"id": len(PD["acts"])}})
    return FakeResp(404, {"success": False, "error": "not found"})
def _fake_hubspot(method, url, headers, params, body):
    path = urlparse(url).path
    HS["calls"].append((method, path, body))
    if headers.get("Authorization") != "Bearer hstok": return FakeResp(401, {"message": "Authentication credentials not valid"})
    if HS["fail"] > 0:
        HS["fail"] -= 1; return FakeResp(429, {"message": "rate limit"})
    if path == "/crm/v3/objects/contacts" and method == "GET": return FakeResp(200, {"results": []})
    if path == "/crm/v3/objects/contacts/search":
        v = body["filterGroups"][0]["filters"][0]["value"]
        return FakeResp(200, {"results": [{"id": c["id"]} for c in HS["contacts"] if c["properties"]["phone"] == v][:1]})
    if path == "/crm/v3/objects/contacts" and method == "POST":
        cid = str(900 + len(HS["contacts"])); HS["contacts"].append({"id": cid, **body}); return FakeResp(201, {"id": cid})
    if path == "/crm/v3/objects/deals" and method == "POST":
        did = str(700 + len(HS["deals"])); HS["deals"][did] = {"id": did, **body}; return FakeResp(201, {"id": did})
    m = re.match(r"/crm/v3/objects/deals/(\d+)$", path)
    if m and method == "PATCH": HS["deals"][m[1]]["properties"].update(body["properties"]); return FakeResp(200, {"id": m[1]})
    if path.startswith("/crm/v4/objects/deals/") and "/associations/default/contacts/" in path and method == "PUT": HS["assoc"].append(path); return FakeResp(200, {})
    if path == "/crm/v3/objects/notes": HS["notes"].append(body); return FakeResp(201, {"id": str(len(HS["notes"]))})
    return FakeResp(404, {"message": "not found"})
def _usage(): return NS(input_tokens=USAGE["in"], output_tokens=USAGE["out"], cache_read_input_tokens=USAGE["cr"], cache_creation_input_tokens=USAGE["cw"])
def _text(t): return NS(stop_reason="end_turn", content=[NS(type="text", text=t)], usage=_usage())
class _Msgs:
    async def create(self, **k):
        system = "\n".join(b["text"] for b in k["system"]) if isinstance(k["system"], list) else k["system"]
        last = k["messages"][-1]["content"]
        if "Você simula um cliente brasileiro" in system:                # cliente simulado da avaliação
            CALLS.append({"kind": "sim", "tools": 0, "system": system})
            return _text(EVALSIM["lead"](system, k["messages"]))
        if "avaliador rigoroso" in system:                                # juiz da avaliação
            CALLS.append({"kind": "juiz", "tools": 0, "system": system, "user": last})
            if EVALSIM["judge_fail"]: raise RuntimeError("juiz fora do ar")
            return _text(EVALSIM["judge_raw"] or json.dumps({"precisao": 4, "qualificacao": 4, "tom": 5, "conducao": 4, "fechamento": 3, "violacoes": [], "resumo": "bom atendimento"}))
        if "RASCUNHO DE AGENTE SDR" in system:
            CALLS.append({"kind": "rascunho", "tools": 0, "system": system, "user": last})
            return _text("ABERTURA: Oi {nome}! Aqui é {agente}, assistente virtual da Vida Mais. Posso te ajudar a comparar planos?\n---\nOlá {nome}, sou {agente}, assistente virtual da Vida Mais. Posso fazer 3 perguntas rápidas? Se não quiser receber mensagens, responda SAIR.\n---\n{nome}, {agente} aqui, da Vida Mais (assistente virtual). Quer ver opções de plano?\n---\nOi {nome}, {agente}, assistente virtual da Vida Mais. Posso te chamar para uma conversa rápida?")
        if "VARIAÇÕES DE ABERTURA" in system:
            CALLS.append({"kind": "variacoes", "tools": 0, "system": system})
            return _text("Oi {nome}! Aqui é a Ana, assistente virtual da Vida Mais. Posso te ajudar a comparar planos? Se não quiser receber mensagens, responda SAIR.\n---\nOlá {nome}, tudo bem? Sou a Ana, assistente virtual da Vida Mais, e vi seu pedido de cotação. Posso fazer 3 perguntas rápidas?\n---\n{nome}, aqui é a Ana, assistente virtual da Vida Mais. Quer ver as opções de plano de saúde? Se não quiser receber mensagens, responda SAIR.")
        if "RESUMO DE MEMÓRIA" in system:
            CALLS.append({"kind": "memoria", "tools": 0, "system": system, "user": last})
            return _text(MEMSIM["fn"](last))
        if "Você transcreve documentos" in system:                         # PDF da base de conhecimento
            CALLS.append({"kind": "kbpdf", "tools": 0, "system": system})
            return _text(PDFSIM["fn"](k))
        CALLS.append({"kind": "leitura" if "Você lê arquivos" in system else "abertura" if "PRIMEIRA mensagem" in system
                      else "sugestao" if "SUGERINDO" in system else "agente", "tools": len(k.get("tools") or []), "system": system})
        if "Você lê arquivos" in system: return _text("Notificação de Penalidade por excesso de velocidade (radar), São Paulo/SP. Prazo para recurso: 16/10.")
        if "RETOMADA" in system: return _text("Oi! Ficou alguma dúvida sobre o que conversamos? Posso te ajudar com o próximo passo.")
        if "PRIMEIRA mensagem" in system: return _text("Oi! Aqui é a Ana, assistente virtual. Vi seu pedido de análise. Pode me enviar uma foto da notificação? Se não quiser receber mensagens, responda SAIR.")
        if "SUGERINDO" in system: return _text("Obrigada! Qual é a data-limite escrita na notificação?")
        if isinstance(last, list) and last and isinstance(last[0], dict) and last[0].get("type") == "tool_result":
            return _text("Perfeito, anotei tudo! Um especialista vai te retornar por aqui.")
        t = (last if isinstance(last, str) else "").lower()
        if AGENT_HOOK["fn"]:
            hooked = AGENT_HOOK["fn"](t, system)
            if hooked: return _text(hooked)
        if "manda o catálogo" in t and any(x["name"] == "enviar_material" for x in (k.get("tools") or [])):
            return NS(stop_reason="tool_use", usage=_usage(), content=[NS(type="tool_use", id="tm1", name="enviar_material", input={"nome": "Catálogo 2026", "mensagem": "Segue!"})])
        if "quero fechar" in t and any(x["name"] == "gerar_link_pagamento" for x in (k.get("tools") or [])):
            return NS(stop_reason="tool_use", usage=_usage(), content=[NS(type="tool_use", id="tp1", name="gerar_link_pagamento", input=dict(PAYSIM.get("tool_input") or {}))])
        if "campinas" in t or "moramos" in t:
            return NS(stop_reason="tool_use", usage=_usage(), content=[
                NS(type="tool_use", id="t1", name="atualizar_crm", input={"stage": "qualificando", "campos": {"cidade": "Campinas", "temperatura": "quente"}}),
                NS(type="tool_use", id="t2", name="encaminhar_ao_vendedor", input={"resumo": "[QUENTE] casal, Campinas"})])
        return _text("Entendi! E qual é a sua cidade?")
class AsyncAnthropic:
    def __init__(self, **k): self.messages = _Msgs()

def _mod(name, **kw):
    m = types.ModuleType(name); m.__dict__.update(kw); sys.modules[name] = m; return m

def load_server(env=None):
    for k, v in {**DEFAULT_ENV, **(env or {})}.items():     # variáveis já definidas no ambiente têm prioridade sobre os padrões
        if (env and k in env) or k not in os.environ: os.environ[k] = v
    _mod("fastapi", FastAPI=FastAPI, Request=FakeRequest, BackgroundTasks=BackgroundTasks, HTTPException=HTTPException,
         Header=lambda default=None: _Header(default), Depends=lambda f: _Dep(f))
    _mod("fastapi.responses", HTMLResponse=HTMLResponse, FileResponse=FileResponse, Response=Response)
    _mod("pydantic", BaseModel=BaseModel)
    _mod("httpx", AsyncClient=FakeClient)
    _mod("anthropic", AsyncAnthropic=AsyncAnthropic)
    sys.path.insert(0, ROOT)
    import server
    server.in_window = lambda cfg: True          # o teste não depende do horário do relógio
    with server.conn() as c:                     # o operador já preencheu os campos [CORRETORA] etc. do nicho de exemplo (sem isso o disparo é bloqueado)
        for r in c.execute("SELECT id,prompt,outbound_text FROM niches WHERE name='Planos de saúde'").fetchall():
            c.execute("UPDATE niches SET prompt=?, outbound_text=? WHERE id=?", (server.PLACEHOLDER_RE.sub("Vida Mais", r["prompt"] or ""), server.PLACEHOLDER_RE.sub("Vida Mais", r["outbound_text"] or ""), r["id"]))
    server.set_setting("qr_ack", json.dumps({"version": server.QR_TERMS_VERSION, "name": "Teste", "ts": time.time()}))   # o operador já aceitou o risco do modo QR
    return server

# ---------- ponte HTTP (equivalente simplificado ao que o FastAPI faz) ----------
def _compile(path): return re.compile("^" + re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", path) + "$")

async def call_route(S, method, target, headers, body):
    u = urlparse(target); path, query = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
    if path.startswith("/__test/"): return await control(S, method, path, body)
    for m, pat, fn, kw in ROUTES:
        mt = _compile(pat).match(path)
        if m != method or not mt: continue
        try:
            for dep in kw.get("dependencies", []):
                d = dep.f; sig = inspect.signature(d)
                r = d(**{n: headers.get(n.replace("_", "-"), p.default.default if isinstance(p.default, _Header) else p.default) for n, p in sig.parameters.items()})
                if inspect.isawaitable(r): await r
            jb = json.loads(body) if body and headers.get("content-type", "").startswith("application/json") else {}
            bg, kwargs = BackgroundTasks(), {}
            for n, p in inspect.signature(fn).parameters.items():
                a, d = p.annotation, p.default
                if a is FakeRequest: kwargs[n] = FakeRequest(headers, body, query)
                elif a is BackgroundTasks: kwargs[n] = bg
                elif isinstance(d, _Header): kwargs[n] = headers.get(n.replace("_", "-"), d.default)
                elif n in mt.groupdict(): kwargs[n] = int(mt[n]) if a is int else mt[n]
                elif isinstance(a, type) and issubclass(a, BaseModel):
                    try: kwargs[n] = a(**jb)
                    except ValueError as e: return 422, "application/json", json.dumps({"detail": str(e)}).encode()
                elif a is dict: kwargs[n] = jb
                elif n in query: kwargs[n] = a(query[n]) if a in (int, float) else query[n]
            res = fn(**kwargs)
            if inspect.isawaitable(res): res = await res
            async def run_bg():
                for f, a, k in bg.tasks:
                    try:
                        r = f(*a, **k)
                        if inspect.isawaitable(r): await r
                    except Exception as e: print("[erro em tarefa de fundo]", repr(e), file=sys.stderr)
            if bg.tasks: asyncio.create_task(run_bg())
            if isinstance(res, Response):
                return 200, res.media_type, res.content if isinstance(res.content, bytes) else res.content.encode()
            if isinstance(res, FileResponse):
                return 200, mimetypes.guess_type(res.path)[0] or "application/octet-stream", open(res.path, "rb").read()
            if kw.get("response_class") is HTMLResponse: return 200, "text/html; charset=utf-8", res.encode()
            return 200, "application/json", json.dumps(res).encode()
        except HTTPException as e:
            return e.status_code, "application/json", json.dumps({"detail": e.detail}).encode()
        except Exception as e:
            import traceback; traceback.print_exc()
            return 500, "application/json", json.dumps({"detail": repr(e)}).encode()
    return 404, "application/json", b'{"detail":"Not Found"}'

async def control(S, method, path, body):
    j = json.loads(body) if body else {}
    if path == "/__test/notice":             # aviso do operador (faixa no topo do painel)
        S.NOTICE_FILE = S.Path(TMP) / "aviso.json"
        if j: S.NOTICE_FILE.write_text(json.dumps(j), encoding="utf-8")
        elif S.NOTICE_FILE.exists(): S.NOTICE_FILE.unlink()
        return 200, "application/json", b"{}"
    if path == "/__test/sent": return 200, "application/json", json.dumps(SENT).encode()
    if path == "/__test/calls": return 200, "application/json", json.dumps([{k: v for k, v in c.items() if k != "system"} for c in CALLS]).encode()
    if path == "/__test/photo":
        PHOTO["have"].update(j.get("have", [])); return 200, "application/json", b"{}"
    if path == "/__test/gateway":
        ln = j.pop("line", "main")
        tgt = GW if ln == "main" else GWL.setdefault(ln, {"state": "qr", "me": "5521999991111"})
        tgt.update({k: v for k, v in j.items() if k in tgt}); return 200, "application/json", json.dumps({"main": GW, **GWL}).encode()
    if path == "/__test/tick":               # força um ciclo da fila de envio (sem esperar o intervalo)
        S.NEXT_AT = 0; S.LINE_NEXT.clear(); S.LINE_STATE_TS = 0; await S.outbox_tick()
        with S.conn() as c: rows = [dict(r) for r in c.execute("SELECT phone,status,error FROM outbox ORDER BY id")]
        return 200, "application/json", json.dumps(rows).encode()
    if path == "/__test/scan":
        n = await S.followup_scan(); return 200, "application/json", json.dumps({"queued": n}).encode()
    if path == "/__test/sla":
        n = await S.sla_scan(); return 200, "application/json", json.dumps({"reminders": n}).encode()
    if path == "/__test/crm": return 200, "application/json", json.dumps([{**c, "body": c["body"].decode() if c["body"] else ""} for c in CRM]).encode()
    if path == "/__test/pd":
        PD["fail"] = j.get("fail", PD["fail"]) if j else PD["fail"]; return 200, "application/json", json.dumps({k: v for k, v in PD.items()}, default=str).encode()
    if path == "/__test/hooks": return 200, "application/json", json.dumps(HOOKS).encode()
    if path == "/__test/mail": return 200, "application/json", json.dumps(MAIL).encode()
    if path == "/__test/db":
        with S.conn() as c: rows = [dict(r) for r in c.execute(j["sql"], j.get("args", []))]
        return 200, "application/json", json.dumps(rows).encode()
    return 404, "application/json", b"{}"

async def serve(port):
    S = load_server()
    async def noop(): return
    S.automation_loop = noop
    S.outbox_loop = noop                      # o ciclo da fila é disparado manualmente pelos testes (/__test/tick)
    for fn in STARTUP: await fn()
    async def handle(reader, writer):
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
            method, target, _ = head[0].split(" ")
            headers = {k.strip().lower(): v.strip() for k, v in (h.split(":", 1) for h in head[1:] if ":" in h)}
            n = int(headers.get("content-length", "0")); body = await reader.readexactly(n) if n else b""
            status, ctype, payload = await call_route(S, method, target, headers, body)
            if not target.startswith("/__test/"):      # o middleware de auditoria do servidor real (aqui chamado à mão)
                S.audit_request(method, urlparse(target).path, headers.get("x-token", ""), status, "127.0.0.1")
        except Exception as e:
            status, ctype, payload = 500, "text/plain", repr(e).encode()
        writer.write(f"HTTP/1.1 {status} X\r\nContent-Type: {ctype}\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
        await writer.drain(); writer.close()
    srv = await asyncio.start_server(handle, "127.0.0.1", port)
    print(f"harness em http://127.0.0.1:{port}", flush=True)
    async with srv: await srv.serve_forever()

if __name__ == "__main__":
    asyncio.run(serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765))
