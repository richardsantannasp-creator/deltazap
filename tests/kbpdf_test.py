"""PDF na base de conhecimento: leitura fiel em blocos, rascunho para conferir, conferência automática dos valores em reais."""
import asyncio, base64, os, sys, tempfile
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
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0
def make_pdf(pages):
    """PDF mínimo com camada de texto (uma linha por página)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for i, t in enumerate(pages):
        pid, cid = 4 + 2 * i, 5 + 2 * i
        kids.append(f"{pid} 0 R")
        while len(objs) < pid - 1: objs.append(None)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {cid} 0 R /Resources << /Font << /F1 3 0 R >> >> >>")
        stream = f"BT /F1 12 Tf 72 700 Td ({t}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    out = b"%PDF-1.4\n"; offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode()
    return out
b64 = lambda b: base64.b64encode(b).decode()
async def main():
    S = harness.load_server()
    pdf = make_pdf(["Plano Ouro R$ 1.234,56 por mes", "Plano Prata R$ 890,00 carencia 30 dias"])
    harness.PDFSIM["fn"] = lambda k: "# Planos\n| Plano | Valor |\n|---|---|\n| Ouro | R$ 1.234,56 |\n| Prata | R$ 890,00 |"
    n0 = len(q(S, "SELECT 1 FROM kb_docs"))
    r = await S.kb_pdf(S.KbPdfIn(niche_id=1, filename="Tabela Planos 2026.pdf", data=b64(pdf)))
    check("devolve o rascunho com título, tabela e nº de páginas", r["title"] == "Tabela Planos 2026" and "| Ouro | R$ 1.234,56 |" in r["body"] and r["pages"] == 2, r)
    check("valores conferem: sem avisos", r["warnings"] == [], r["warnings"])
    check("nada foi salvo (é só rascunho)", len(q(S, "SELECT 1 FROM kb_docs")) == n0)
    # transcrição que erra um valor
    harness.PDFSIM["fn"] = lambda k: "| Ouro | R$ 1.243,56 |\n| Prata | R$ 890,00 |"
    r = await S.kb_pdf(S.KbPdfIn(niche_id=1, filename="t.pdf", data=b64(pdf)))
    w = " ".join(r["warnings"])
    check("valor trocado na transcrição é apontado nos dois sentidos", "1.234,56" in w and "1.243,56" in w, r["warnings"])
    # trecho ilegível
    harness.PDFSIM["fn"] = lambda k: "| Ouro | R$ 1.234,56 |\n| Prata | [ilegível] 890,00 |"
    r = await S.kb_pdf(S.KbPdfIn(niche_id=1, filename="t.pdf", data=b64(pdf)))
    check("trecho [ilegível] gera aviso", any("ilegível" in x for x in r["warnings"]), r["warnings"])
    # blocos: 14 páginas = 3 chamadas de 6 páginas
    big = make_pdf([f"Pagina {i} R$ {i + 10},00" for i in range(14)])
    calls = []
    harness.PDFSIM["fn"] = lambda k: (calls.append(1) or f"bloco {len(calls)}: " + " ".join(f"R$ {i + 10},00" for i in range(14)))
    r = await S.kb_pdf(S.KbPdfIn(niche_id=1, filename="grande.pdf", data=b64(big)))
    check("PDF grande é lido em blocos de 6 páginas e juntado na ordem", len(calls) == 3 and r["body"].index("bloco 1") < r["body"].index("bloco 3") and r["pages"] == 14, (len(calls), r["pages"]))
    # sem camada de texto (nenhum texto extraído)
    blank = make_pdf([""])
    harness.PDFSIM["fn"] = lambda k: "tabela lida da imagem"
    r = await S.kb_pdf(S.KbPdfIn(niche_id=1, filename="escaneado.pdf", data=b64(blank)))
    check("sem camada de texto: avisa que os valores precisam de conferência manual", any("escaneado" in x for x in r["warnings"]), r["warnings"])
    # validações
    check("não é .pdf: 400", await err(S.kb_pdf(S.KbPdfIn(niche_id=1, filename="x.txt", data=b64(b"oi")))) == 400)
    check("arquivo .pdf que não é PDF: 400", await err(S.kb_pdf(S.KbPdfIn(niche_id=1, filename="x.pdf", data=b64(b"nao sou pdf")))) == 400)
    check("PDF grande demais: 400", await err(S.kb_pdf(S.KbPdfIn(niche_id=1, filename="x.pdf", data=b64(b"%PDF" + b"0" * 15_100_000)))) == 400)
    check("nicho inexistente: 404", await err(S.kb_pdf(S.KbPdfIn(niche_id=999, filename="x.pdf", data=b64(pdf)))) == 404)
    many = make_pdf(["p"] * 61)
    check("mais de 60 páginas: 400", await err(S.kb_pdf(S.KbPdfIn(niche_id=1, filename="x.pdf", data=b64(many)))) == 400)
    # fluxo completo: o operador confere e salva; o agente passa a enxergar os valores
    harness.PDFSIM["fn"] = lambda k: "| Ouro | R$ 1.234,56 |\n| Prata | R$ 890,00 |\nCarência de 30 dias para consultas."
    r = await S.kb_pdf(S.KbPdfIn(niche_id=1, filename="Planos.pdf", data=b64(pdf)))
    await S.kb_add(S.KbIn(niche_id=1, title=r["title"], body=r["body"]))
    S.upsert_lead("5521977772222", "Ana", niche_id=1)
    sys_txt = "\n".join(b_["text"] for b_ in S.build_system(S.get_lead("5521977772222"), S.get_niche(1), "quanto custa o plano ouro?"))
    check("depois de salvo, o agente enxerga os valores e as regras", "R$ 1.234,56" in sys_txt and "Carência de 30 dias" in sys_txt)
    check("o custo da leitura aparece como «leitura» na aba Custos", q(S, "SELECT 1 FROM usage WHERE kind='leitura'"))
    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
