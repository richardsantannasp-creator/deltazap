"""Testa catálogo e base de conhecimento por nicho: preço oficial, recuperação por trechos, cópia/exclusão, importação e o que chega ao prompt do agente."""
import asyncio, base64, json, os, sys, tempfile
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
async def err(coro):
    try: await coro
    except harness.HTTPException as e: return e.status_code
    return 0

async def main():
    S = harness.load_server()
    P = lambda **k: S.ProductIn(**{"niche_id": 1, "name": "Plano Ouro", "price": "R$ 1.234,56", **k})

    # ---------- preço e validações ----------
    pp = S.parse_price
    check("preço: formatos brasileiros e simples", (pp("R$ 1.234,56"), pp("197,90"), pp("99"), pp("1234.56"), pp("1.500"), pp("0,99")) == (123456, 19790, 9900, 123456, 150000, 99), [pp("R$ 1.234,56"), pp("197,90"), pp("99"), pp("1234.56"), pp("1.500"), pp("0,99")])
    check("preço inválido/zero/negativo vira None", pp("abc") is None and pp("0") is None and pp("") is None and pp("-5") is None)
    check("brl formata", S.brl(123456) == "R$ 1.234,56" and S.brl(99) == "R$ 0,99" and S.brl(1000000) == "R$ 10.000,00")
    check("produto: nome vazio, preço ruim, link http, desconto > 50 são recusados",
          await err(S.product_add(P(name=" "))) == 400 and await err(S.product_add(P(price="grátis"))) == 400
          and await err(S.product_add(P(pay_url="http://x.com/p"))) == 400 and await err(S.product_add(P(max_discount_pct=60))) == 400)
    check("produto em nicho inexistente -> 404", await err(S.product_add(P(niche_id=999))) == 404)
    r = await S.product_add(P(description="Cobertura nacional", unit="mês", max_discount_pct=5, pay_url="https://pagar.exemplo/ouro"))
    r2 = await S.product_add(P(name="Plano Prata", price="89,90", description="Cobertura regional"))
    row = q(S, "SELECT * FROM products WHERE id=?", r["id"])[0]
    check("produto guardado em centavos", row["price_cents"] == 123456 and row["max_discount_pct"] == 5 and row["unit"] == "mês", row)
    await S.product_edit(r2["id"], P(name="Plano Prata", price="79,90", description="Cobertura regional"))
    check("editar produto muda o preço", q(S, "SELECT price_cents c FROM products WHERE id=?", r2["id"])[0]["c"] == 7990)

    # ---------- o catálogo chega ao prompt (parte fixa, em cache) ----------
    lead = {"phone": "5511900000001", "name": "Ana", "company": "", "origin": "receptivo", "stage": "novo", "bant": "{}", "variant": "A"}
    blocks = S.build_system(lead, S.get_niche(1), "")
    st = blocks[0]["text"]
    check("catálogo no bloco fixo com id e preço oficial", "CATÁLOGO" in st and f"[#{r['id']}] Plano Ouro — R$ 1.234,56 / mês" in st and "R$ 79,90" in st, st[-600:])
    check("regras de venda presentes", "REGRAS DE VENDA" in st and "gerar_link_pagamento" in st)
    check("desconto máximo aparece só para quem tem", "desconto máximo autorizado: 5%" in st and st.count("desconto máximo autorizado") == 1)
    check("bloco fixo continua com cache", blocks[0].get("cache_control"))

    S2 = await S.niche_create(S.NicheIn(name="Vazio", prompt="Você é a Bia.", outbound_text="Oi {nome}. Responda SAIR para parar."))
    b2 = S.build_system(lead, S.get_niche(S2["id"]), "")
    check("nicho sem catálogo/base não ganha regras de venda (comportamento antigo)", "REGRAS DE VENDA" not in b2[0]["text"] and "CATÁLOGO" not in b2[0]["text"])

    # ---------- base de conhecimento ----------
    check("documento sem título/curto/nicho errado é recusado", await err(S.kb_add(S.KbIn(niche_id=1, title="", body="texto longo ok"))) == 400
          and await err(S.kb_add(S.KbIn(niche_id=1, title="x", body="ab"))) == 400 and await err(S.kb_add(S.KbIn(niche_id=999, title="x", body="texto longo ok"))) == 404)
    d1 = await S.kb_add(S.KbIn(niche_id=1, title="Garantia", body="A garantia dos planos é de 12 meses contra defeitos de cobertura. Reembolso em até 7 dias."))
    st = S.build_system(lead, S.get_niche(1), "")[0]["text"]
    check("base pequena entra inteira no bloco fixo", "BASE DE CONHECIMENTO DO NICHO" in st and "12 meses" in st)
    info = await S.kb_list(1)
    check("lista mostra modo e tamanho", info["mode"] == "completa" and info["chars"] > 50 and len(info["docs"]) == 1 and len(info["products"]) == 2, info)

    big = "\n\n".join(f"Capítulo {i}: assunto aleatório numero {i} sobre tema {i} " + ("lorem ipsum " * 40) for i in range(40))
    await S.kb_add(S.KbIn(niche_id=1, title="Manual grande", body=big))
    await S.kb_add(S.KbIn(niche_id=1, title="Entrega", body="O prazo de entrega para Campinas é de 3 dias úteis e o frete é grátis acima de R$ 200."))
    info = await S.kb_list(1)
    check("base grande muda para modo por trechos", info["mode"] == "por trechos", info)
    blocks = S.build_system(lead, S.get_niche(1), "qual o prazo de entrega para Campinas?")
    check("trechos relacionados vão no bloco dinâmico (fora do cache)", "prazo de entrega para Campinas" in blocks[1]["text"] and "TRECHOS DA BASE" in blocks[1]["text"] and "3 dias úteis" not in blocks[0]["text"], blocks[1]["text"][:300])
    check("trechos sem relação não entram", "Capítulo 17" not in blocks[1]["text"])
    check("busca ignora acento e plural", "garantia" in S.build_system(lead, S.get_niche(1), "qual é a GARANTÍA dos planos?")[1]["text"].lower())
    b0 = S.build_system(lead, S.get_niche(1), "xyzzy qwerty")
    check("pergunta sem nada parecido não quebra e não traz lixo", "Capítulo" not in b0[1]["text"] and b0[0]["text"])
    check("tamanho dos trechos respeita o orçamento", len(S.build_system(lead, S.get_niche(1), "capitulo assunto aleatorio tema lorem ipsum")[1]["text"]) < S.KB_BUDGET + 2500)

    # ---------- catálogo grande entra parcial ----------
    for i in range(45):
        await S.product_add(P(name=f"Camiseta modelo {i}", price="49,90", description="algodão azul" if i % 2 else "poliéster preto"))
    st = S.build_system(lead, S.get_niche(1), "queria uma camiseta azul")
    check("catálogo > 40 sai do bloco fixo e vem filtrado pela conversa", "CATÁLOGO PARCIAL" in st[1]["text"] and "CATÁLOGO (" not in st[0]["text"], st[1]["text"][:200])
    check("catálogo parcial limita a 15 itens", st[1]["text"].count("[#") <= 15)
    await S.product_edit(r2["id"], P(name="Plano Prata", price="79,90", active=False))
    q(S, "UPDATE products SET active=0 WHERE name LIKE 'Camiseta%'")
    st = S.build_system(lead, S.get_niche(1), "")[0]["text"]
    check("produto inativo some do prompt", "Plano Prata" not in st and "Camiseta" not in st and "Plano Ouro" in st)

    # ---------- importação ----------
    csvt = "nome;preço;descrição;link;desconto_max;unidade\nCurso Básico;R$ 297,00;Acesso por 1 ano;https://pagar.exemplo/b;10;ano\nBrinde;grátis;;;;\nCurso Pro,497.00,Com mentoria,,,\n"
    imp = await S.product_import(S.ProductImportIn(niche_id=2, text=csvt))
    check("importação de produtos: aceita ; e vírgula, aponta linha com erro", imp["added"] == 2 and len(imp["errors"]) == 1 and "linha 3" in imp["errors"][0], imp)
    pr = q(S, "SELECT * FROM products WHERE niche_id=2 ORDER BY id")
    check("importação grava preço, link, desconto e unidade", pr[0]["price_cents"] == 29700 and pr[0]["max_discount_pct"] == 10 and pr[0]["pay_url"].startswith("https://") and pr[0]["unit"] == "ano" and pr[1]["price_cents"] == 49700, pr)
    enc = lambda t: base64.b64encode(t.encode()).decode()
    check("importar arquivo de texto cria documento", len((await S.kb_import(S.KbImportIn(niche_id=2, filename="faq.md", data=enc("# FAQ\nPergunta: horário? Resposta: 9h às 18h.")))) ["ids"]) == 1)
    check("importar PDF/Word é recusado com orientação", await err(S.kb_import(S.KbImportIn(niche_id=2, filename="a.pdf", data=enc("x")))) == 400)
    r = await S.kb_import(S.KbImportIn(niche_id=2, filename="grande.txt", data=enc("palavra " * 20000)))
    check("arquivo grande é dividido em documentos de até 50 mil caracteres", len(r["ids"]) >= 3 and max(len(q(S, "SELECT body FROM kb_docs WHERE id=?", i)[0]["body"]) for i in r["ids"]) <= 50000)
    h = await S.kb_import(S.KbImportIn(niche_id=2, filename="p.html", data=enc("<html><script>evil()</script><body><p>Entrega rápida</p></body></html>")))
    body = q(S, "SELECT body FROM kb_docs WHERE id=?", h["ids"][0])[0]["body"]
    check("HTML: remove scripts e tags", "evil" not in body and "<p>" not in body and "Entrega rápida" in body, body)

    # ---------- cópia, exclusão, prévia, edição ----------
    n3 = await S.niche_create(S.NicheIn(name="Cópia do 2", copy_from=2))
    check("duplicar nicho copia catálogo e base", len(q(S, "SELECT 1 FROM products WHERE niche_id=?", n3["id"])) == 2 and len(q(S, "SELECT 1 FROM kb_docs WHERE niche_id=?", n3["id"])) >= 3)
    await S.niche_delete(n3["id"])
    check("excluir nicho apaga catálogo e base dele", not q(S, "SELECT 1 FROM products WHERE niche_id=?", n3["id"]) and not q(S, "SELECT 1 FROM kb_docs WHERE niche_id=?", n3["id"]))
    check("o outro nicho não foi afetado", len(q(S, "SELECT 1 FROM products WHERE niche_id=2")) == 2)
    pv = await S.kb_preview(1, "qual o prazo de entrega para Campinas?")
    check("prévia mostra o que o agente enxerga", "Plano Ouro" in pv["fixo"] and "Campinas" in pv["da_conversa"], pv)
    await S.kb_edit(d1["id"], S.KbIn(niche_id=1, title="Garantia", body="Garantia de 24 meses."))
    check("editar documento", "24 meses" in (await S.kb_get(d1["id"]))["body"])
    await S.kb_del(d1["id"])
    check("apagar documento", not q(S, "SELECT 1 FROM kb_docs WHERE id=?", d1["id"]))

    # ---------- integração com o agente e resistência a falhas ----------
    harness.CALLS.clear()
    await S.handle_incoming("5511977770001", "Caio", "oi, quanto custa o plano ouro?", None, False)
    sysmsg = harness.CALLS[-1]["system"] if harness.CALLS else ""
    check("o agente recebe catálogo e regras de venda na chamada ao Claude", "Plano Ouro — R$ 1.234,56" in sysmsg and "REGRAS DE VENDA" in sysmsg, sysmsg[-300:])
    orig = S.sales_context
    def boom(*a, **k): raise RuntimeError("falha simulada")
    S.sales_context = boom
    blk = S.build_system(lead, S.get_niche(1), "")
    S.sales_context = orig
    check("erro na base não derruba o atendimento", len(blk) == 2 and "PAPEL" in blk[0]["text"] or blk[0]["text"])

    print(f"\n{OK} ok, {FAIL} falha(s)")
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
