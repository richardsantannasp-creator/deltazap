"""
Enriquecimento pelo site da própria empresa.

Abre a página inicial (e, se preciso, a página de contato) do site que a empresa
cadastrou no Google e procura:
  - links de WhatsApp (wa.me, api.whatsapp.com, web.whatsapp.com, whatsapp://)
  - e-mail comercial
  - perfil do Instagram
O número de WhatsApp que a empresa divulga no próprio site é muito mais
confiável do que deduzir pelo formato do telefone.
"""

import hashlib
import random
import re
from datetime import datetime
from urllib.parse import unquote, urljoin, urlparse

import ipaddress
import socket

import requests

from places_core import ORIGEM_SITE, normalizar_telefone_br

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
NAO_VISITAR = ("instagram.com", "facebook.com", "fb.com", "wa.me", "whatsapp.com", "google.", "goo.gl",
               "linkedin.com", "tiktok.com", "youtube.com", "twitter.com", "x.com", "ifood.com")
MAX_BYTES = 1_500_000

RE_WA = re.compile(r"(?:https?:)?(?:\\?/){2}(?:wa\.me|(?:api|web|chat)\.whatsapp\.com)[^\s\"'<>)]*"
                   r"|whatsapp://send[^\s\"'<>)]*", re.I)
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
RE_INSTA = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I)
RE_CONTATO = re.compile(r"href=[\"']([^\"'#]*(?:contato|fale-conosco|faleconosco|contact|atendimento)[^\"'#]*)[\"']", re.I)
INSTA_IGNORAR = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "share", "about",
                 "developer", "legal", "direct", "web", "instagram"}
EMAIL_IGNORAR = ("sentry", "example", "exemplo", "wixpress", "domain.com", "seuemail", "seu@", "email.com",
                 "@2x", "user@", "nome@", "teste@", "godaddy", "cloudflare")


def _numero_de_link(url):
    u = unquote(url.replace("\\/", "/").replace("&amp;", "&"))
    if "chat.whatsapp.com" in u:  # convite de grupo, não é número
        return ""
    m = re.search(r"wa\.me/\+?(\d[\d\s-]{8,18})", u) or re.search(r"phone=\+?([\d\s()-]{8,20})", u)
    if not m:
        return ""
    d = re.sub(r"\D", "", m.group(1))
    if len(d) in (12, 13) and d.startswith("55"):
        return "+" + d
    if len(d) in (10, 11):
        return d  # sem o 55: trata como número nacional
    return "+" + d


def extrair(html):
    """Retorna (lista de WhatsApp em E.164, lista de e-mails, lista de @instagram)."""
    whats = []
    for m in RE_WA.finditer(html):
        n = _numero_de_link(m.group(0))
        if n:
            e164, tipo = normalizar_telefone_br(n)
            if e164 and tipo != "Desconhecido" and e164 not in whats:
                whats.append(e164)
    emails = []
    for m in re.findall(r"mailto:([^\"'?<>\s]+)", html, re.I) + RE_EMAIL.findall(html):
        e = unquote(m).strip().lower()
        if (RE_EMAIL.fullmatch(e) and e not in emails and not any(x in e for x in EMAIL_IGNORAR)
                and not re.search(r"\.(png|jpe?g|gif|webp|svg|css|js)$", e)):
            emails.append(e)
    insta = []
    for h in RE_INSTA.findall(html):
        h = h.rstrip(".")
        if h.lower() not in INSTA_IGNORAR and h.lower() not in [x.lower() for x in insta]:
            insta.append(h)
    return whats, emails, insta


def url_publica(url):
    """Só http/https para endereços públicos (o site vem do Google, mas pode apontar para a rede interna do servidor)."""
    try:
        pu = urlparse(url)
        if pu.scheme not in ("http", "https") or not pu.hostname:
            return False
        for info in socket.getaddrinfo(pu.hostname, pu.port or 80, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False
        return True
    except (OSError, ValueError):
        return False


def _baixar(sessao, url, timeout):
    r = None
    for _ in range(4):  # redirecionamentos seguidos à mão, validando cada destino
        if not url_publica(url):
            return None, url
        r = sessao.get(url, timeout=timeout, allow_redirects=False, stream=True)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            url = urljoin(url, r.headers["Location"])
            r.close()
            continue
        break
    else:
        return None, url
    tipo = r.headers.get("Content-Type", "")
    if r.status_code >= 400 or (tipo and "html" not in tipo):
        r.close()
        return None, url
    corpo = r.raw.read(MAX_BYTES, decode_content=True)
    r.close()
    return corpo.decode(r.encoding if r.encoding and "8859" not in r.encoding else "utf-8", errors="ignore"), url


def enriquecer_site(url, timeout=8, demo=False):
    out = {"whatsapp": "", "email": "", "instagram": "", "erro": ""}
    if not url:
        return out
    if not url.startswith("http"):
        url = "http://" + url
    host = urlparse(url).netloc.lower()
    if "instagram.com" in host:
        m = RE_INSTA.search(url)
        out["instagram"] = m.group(1) if m else ""
        return out
    if any(h in host for h in NAO_VISITAR):
        return out
    if demo:
        rng = random.Random(hashlib.md5(url.encode()).hexdigest())
        if rng.random() < 0.6:
            out["whatsapp"] = f"+55119{rng.randint(10000000, 99999999)}"
        if rng.random() < 0.55:
            out["email"] = f"contato@{host}"
        if rng.random() < 0.45:
            out["instagram"] = host.split(".")[0].replace("-", "_")
        return out

    sessao = requests.Session()
    sessao.headers.update({"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    fila, vistos = [url], set()
    whats, emails, insta = [], [], []
    while fila and len(vistos) < 2:
        u = fila.pop(0)
        if u in vistos:
            continue
        vistos.add(u)
        try:
            html, final = _baixar(sessao, u, timeout)
        except requests.RequestException as e:
            out["erro"] = type(e).__name__
            continue
        if not html:
            continue
        w, e, i = extrair(html)
        whats += [x for x in w if x not in whats]
        emails += [x for x in e if x not in emails]
        insta += [x for x in i if x not in insta]
        if not whats and len(vistos) == 1:  # tenta a página de contato
            for m in RE_CONTATO.finditer(html):
                link = urljoin(final, m.group(1))
                if urlparse(link).netloc == urlparse(final).netloc:
                    fila.append(link)
                    break
    # prefere celular; WhatsApp Business também roda em fixo
    celulares = [w for w in whats if normalizar_telefone_br(w)[1] == "Celular"]
    out["whatsapp"] = (celulares or whats or [""])[0]
    dominio = host.removeprefix("www.")
    proprios = [e for e in emails if e.endswith("@" + dominio)]
    out["email"] = (proprios or emails or [""])[0]
    out["instagram"] = (insta or [""])[0]
    return out


def aplicar(linha, dados):
    """Copia o resultado do enriquecimento para a linha (dict)."""
    if dados.get("whatsapp"):
        linha["whatsapp"] = dados["whatsapp"]
        linha["whatsapp_origem"] = ORIGEM_SITE
    if dados.get("email"):
        linha["email"] = dados["email"]
    if dados.get("instagram"):
        linha["instagram"] = dados["instagram"]
    linha["enriquecido_em"] = datetime.now().isoformat(timespec="seconds")
    return linha
