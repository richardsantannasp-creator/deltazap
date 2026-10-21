# SDR multi-nicho no WhatsApp com Claude

Uma ferramenta única com: webhook do WhatsApp, agentes de venda por nicho (editáveis no painel), disparo ativo com escolha do nicho e monitoramento ao vivo.

## Conceito
- **Todo agente é SDR ativo e receptivo.** *Ativo:* você dispara o 1º contato. *Receptivo:* o lead chama primeiro no seu WhatsApp e o agente atende na hora. A regra vale para qualquer nicho, inclusive os novos, porque está embutida no servidor (`BASE_RULES`) e a origem do lead (ativo ou receptivo) vai no contexto de cada conversa.
- **Como o lead receptivo escolhe o agente:** pelas **palavras-chave** de cada nicho (aba Agentes). Quem escrever "plano de saúde", por exemplo, vai para o agente de saúde; sem acerto, cai no **nicho padrão**. O roteamento aparece no log (`ROTEAMENTO`).
- **Agente = nicho.** Cada nicho tem seu prompt, seu texto de 1º contato e (opcional) seu template da Meta. As ferramentas (CRM, agendar, encaminhar ao vendedor, transferir para humano) são as mesmas para todos.
- **Ao disparar, você escolhe o nicho.** O lead fica vinculado a ele e, quando responder, é esse agente que conversa.
- Quem chamar sem ter sido disparado cai no **nicho padrão** (marque na aba Agentes).
- **Base de conhecimento por nicho:** cada agente tem um campo com os fatos que ele pode afirmar (serviços, regras, FAQ, o que NÃO se sabe). O prompt manda o agente nunca inventar o que não estiver ali. Edite no painel, aba Agentes.
- **Nichos prontos em pasta:** tudo em `niches/<nome>/` (`meta.json`, `prompt.txt`, `knowledge.md`) é carregado uma única vez na primeira execução. Já vem o **Limpa Multas**, montado a partir do site limpamultasbr.com.br. Para criar outro, copie a pasta e edite.
- **Arquivos do lead:** foto ou PDF enviado pelo WhatsApp (por exemplo, a notificação da multa) é baixado para `uploads/` e aparece no botão **Arquivos** da conversa. O agente é avisado de que o arquivo chegou.
- Vêm 3 nichos de fábrica (Planos de saúde, Limpa Multas e Modelo em branco). Os dois primeiros são: **Planos de saúde** (prompt de `sdr_prompt.txt`) e **Limpa Multas** (recurso de multas e defesa de CNH). O **Modelo em branco** serve para duplicar e adaptar (energia solar, seguros, educação, imóveis...).

## Rodar (modo simulado, sem WhatsApp)
Requer Python 3.10+.
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env        # preencha ANTHROPIC_API_KEY e DASH_TOKEN
uvicorn server:app --port 8000
```
Abra http://localhost:8000 e informe o DASH_TOKEN.

## Claude no atendimento ativo
- O cérebro do atendimento é o **Claude** (API da Anthropic, `ANTHROPIC_API_KEY`; modelo em `CLAUDE_MODEL`).
- **1º contato personalizado:** em Agentes, marque "Claude personaliza o 1º contato". O Claude reescreve a mensagem-modelo do nicho para cada lead usando nome, empresa e o **contexto** (4º campo da linha de disparo: `telefone;nome;empresa;contexto`). Ele só cita o motivo se estiver no contexto, mantém a identidade da assistente e sempre inclui o "responda SAIR". Se a chamada falhar, usa o texto padrão. Não se aplica a nichos com template da Meta (o template precisa ser aprovado e é fixo).
- **Sugerir resposta:** ao assumir uma conversa, o botão **Sugerir resposta** pede ao Claude a próxima mensagem (com o prompt, a base de conhecimento e o histórico do lead). Ela aparece no campo de texto para você editar e enviar; nada é enviado sozinho.

## Arquivos, PDF, JPG, áudio e vídeo
- **Imagem (JPG, PNG, WebP) e PDF:** o **Claude lê** o arquivo assim que o lead envia e o agente recebe um resumo ("Leitura automática: ..."). Em cada nicho você pode dizer o que extrair (campo "O que o Claude deve extrair"; o Limpa Multas já extrai tipo de notificação, órgão, infração e prazo). O resumo evita copiar CPF, CNH, endereço e dados de cartão. O arquivo original fica salvo e abre pelo botão **Arquivos**. Imagens grandes são reduzidas (Pillow). Um lead novo que começa mandando a foto de uma multa é direcionado ao nicho certo pelo conteúdo lido.
- **Áudio:** o Claude não aceita áudio, então é preciso um serviço de transcrição. Escolha em `STT_PROVIDER`: `local` (Whisper no seu servidor com `pip install faster-whisper`, sem enviar o áudio a terceiros, mais lento em CPU fraca) ou `openai` (API Whisper da OpenAI, rápida, o áudio vai para a OpenAI; exige `OPENAI_API_KEY`). Com `none`, o agente pede que o lead escreva. A transcrição pode errar; o agente confirma os dados críticos.
- **Vídeo (MP4, 3GP, MOV, WebM):** o sistema extrai o **áudio** (transcrito como no item acima) e até 3 **quadros** (início, meio e fim), que o Claude lê; o agente recebe os dois juntos. Precisa do **ffmpeg** instalado (no Docker já vem; fora dele: `sudo apt install ffmpeg`, `brew install ffmpeg` ou `winget install ffmpeg`). Limite de 16 MB por vídeo; áudio de até 5 minutos; `VIDEO_FRAMES` (0 a 5, padrão 3) escolhe quantos quadros ler, e `0` lê só o áudio. Cada quadro é uma chamada de leitura ao Claude, então vídeo custa mais que uma foto. Sem ffmpeg, vídeo corrompido ou grande demais, o vídeo é guardado em **Arquivos** e o agente pede, com educação, que o lead descreva em texto ou mande áudio ou foto. Figurinhas (stickers) e vídeos de visualização única não são lidos.
- A leitura é uma chamada extra ao Claude por arquivo (modelo de `CLAUDE_MODEL`).
- **Testar sem WhatsApp:** no chat, o botão **Anexar arquivo (teste)** simula o lead enviando um PDF, JPG, áudio ou vídeo e mostra a leitura ou transcrição na conversa.
- Outros formatos (Word, Excel) são salvos, mas não lidos.

## Google Agenda

O agente consulta horários livres e cria o evento de verdade em uma agenda do Google (conta de serviço). Passo a passo e limites em **AGENDA-GOOGLE.md**. Painel: Integrações > Google Agenda.

## Recursos da equipe: horário, respostas rápidas, notas e desempenho

- **Horário de atendimento** (Avisos > Equipe): defina os dias e horas em que a equipe humana atende (fuso America/Sao_Paulo, ou `TZ_NAME`). Fora dele, se o lead escrever numa conversa que está com a equipe, ele recebe uma mensagem sua (use `{horario}` e `{volta}`), no máximo uma vez a cada 12 h, e a IA, ao transferir, é orientada a avisar o horário. Se quem atende estiver online, nada é enviado em cima. A IA em si continua atendendo 24 h.
- **Respostas rápidas**: textos prontos (com `{nome}` e `{atendente}`) cadastrados no painel; aparecem num seletor no painel e na tela do atendente.
- **Notas internas**: anotações por lead visíveis só à equipe (painel e tela do atendente). Nunca são enviadas ao lead nem entram no que o agente de IA lê; são apagadas junto com os dados do lead (LGPD).
- **Desempenho**: por atendente, conversas atendidas, mensagens, tempo mediano até a 1ª resposta (a partir de quando recebeu a conversa), espera média na fila e ganhos/perdidos, para 7, 30 ou 90 dias. Cada atendente vê os próprios números de 7 dias no topo da sua tela.
- **Não incluído**: perfis de supervisor/permissões por função, etiquetas e autenticação em dois fatores.

## Materiais, janela de 24 h e novos tipos de mensagem

- **Materiais para enviar**: em Agentes > nicho > "Materiais para enviar" cadastre PDF, imagem, vídeo, áudio, Word/Excel/PowerPoint ou TXT (até 12 MB). O agente passa a enxergar a lista e envia sozinho com a ferramenta `enviar_material` quando o lead pede ou quando ajuda a decidir; o mesmo material não é reenviado ao mesmo lead em 6 h. Funciona no modo QR (conector `/send-media`) e na API oficial (upload de mídia da Meta). Leads de teste não disparam arquivos de verdade.
- **Janela de 24 h (API oficial)**: depois de 24 h sem resposta do lead, a Meta só aceita template aprovado (erro 131047). O sistema marca a mensagem como "não enviada" na conversa, registra um aviso e, em envios manuais/de atendente, devolve erro 409 explicando. No modo QR não existe essa janela.
- **Recebidos**: localização (vira texto com link do mapa), contato compartilhado e resposta de botão/lista viram texto para o agente; reações com emoji são ignoradas; figurinhas continuam como aviso.

## Gestor de equipe (acesso próprio, número próprio, equipe própria)
O administrador cria gestores em **Avisos > Gestores de equipe** (limites de números e de atendentes por gestor). O gestor entra em `/gestor`, conecta o WhatsApp dele, cria os atendentes dele e atende as conversas dos números dele, sem ver nada de outros. Transferências em números do gestor só vão para a equipe dele, e os números dos gestores nunca entram nos disparos do administrador. Detalhes em `GESTOR.md`.

## Transferência para atendente humano (equipe logada)
- **Equipe:** na aba **Avisos > Equipe de atendimento** você cadastra atendentes (nome, usuário, senha, máximo de conversas simultâneas). Eles entram em `https://SEU-DOMINIO/atendente` (página separada: só vê as próprias conversas e a fila, nada de configurações). A senha gerada aparece uma única vez; dá para trocar, desativar ou excluir a qualquer momento.
- **Quando transfere:** a IA transfere sozinha (lead pede uma pessoa, reclama, foge do escopo) ou você clica em **Enviar à equipe** no chat. A IA pausa e a conversa vai para o atendente **disponível** com menos conversas (empate: quem recebeu há mais tempo). Se ninguém estiver disponível, ela fica na **fila**, e a IA avisa o lead com honestidade que a equipe responde assim que possível, sem prometer prazo.
- **Presença:** o atendente fica *disponível* ou *ausente* (botão no topo). Quem fecha a aba ou some por mais de 90 s deixa de receber novas conversas; se ficar ausente por mais de `reassign_min` minutos (padrão 10), as conversas dele voltam para a fila e são entregues a outro.
- **No dia a dia:** o atendente lê a fila antes de assumir, responde (a mensagem sai pelo WhatsApp com o nome dele registrado), transfere para um colega ou para a fila, marca o resultado (ganho, perdido, cotação enviada) ou **devolve à IA**. Ele vê as fotos de perfil, o motivo da transferência, os dados já coletados e os arquivos que o lead mandou. Há aviso sonoro e contador na aba para novas conversas.
- **Regras da fila (Equipe de atendimento):** distribuição automática ligada/desligada; se ninguém atender em X minutos, manter na fila ou a IA voltar a atender (com uma mensagem honesta ao lead).
- **Segurança:** senhas guardadas com hash (PBKDF2), sessão de 7 dias que cai ao trocar a senha ou desativar a pessoa, bloqueio de 10 min após 5 senhas erradas, e o atendente só acessa conversas transferidas a ele ou na fila. Use HTTPS (o Caddy do kit já faz).
- Sem atendentes cadastrados, tudo funciona como antes: a IA pausa e a equipe é avisada pelo WhatsApp.

## Fotos de perfil no chat
- No modo **QR**, a lista de leads, o cabeçalho e cada mensagem mostram a **foto de perfil do WhatsApp** do cliente; as respostas (IA ou operador que assumiu a conversa) mostram a foto do **número conectado**, e em **Números** e **Avisos** aparecem as fotos de cada número e de quem recebe os avisos. Sem foto (ou foto privada), aparecem as iniciais.
- Na **API oficial** a Meta não entrega fotos de perfil: o painel usa as iniciais.
- A foto é consultada só quando a conversa é aberta, fica em cache (24 h; 6 h quando não há foto) e é apagada junto com os dados do contato (**Apagar dados**). A exportação LGPD informa se havia foto guardada. Leads de teste e números desconhecidos nunca são consultados.

## Emojis no chat
O botão 😊 ao lado do campo de mensagem abre um seletor de emojis (rostos, gestos, símbolos e objetos) que insere no ponto do cursor. Os agentes usam emoji com moderação, conforme o prompt de cada nicho.

## Importar planilha de contatos
Em **Disparar > Importar planilha**, envie um `.csv` ou `.xlsx` com a primeira linha de títulos:

| nome | whatsapp | empresa (opcional) | contexto (opcional) |
|---|---|---|---|
| Maria Silva | 11999999999 | Padaria Exemplo | pediu cotação |

- Há um **modelo para baixar** na própria janela. O servidor lê o arquivo, reconhece os títulos (também "telefone", "celular", "cliente" etc.), padroniza os números (acrescenta o 55 quando faltar) e mostra o resumo.
- Ficam de fora, com o motivo na tela: números inválidos ou curtos, repetidos na planilha, quem **já pediu para sair**, quem já está em conversa e quem já está na fila. Números com 12 dígitos entram com aviso (podem ser fixo ou estar sem o 9).
- Se o Excel mostrar o número como `5,51199E+12`, formate a coluna do WhatsApp como **Texto** antes de salvar.
- Os contatos validados vão para a caixa de texto: confira, escolha o nicho, confirme o consentimento e dispare. Eles entram na fila e saem no ritmo configurado. Limite de 2000 contatos por envio e 5 MB por arquivo; `.xls` antigo não é suportado.
- Importe só contatos que consentiram em receber mensagens.

## Testes
- **`python tests/smoke_real.py http://localhost:8000 SEU_DASH_TOKEN`**: teste de fumaça no SEU servidor de verdade. Confere o token, os nichos, cria um lead de teste (nada vai ao WhatsApp), pede uma resposta real ao Claude, a sugestão de resposta, a planilha, o ritmo e as métricas. É o primeiro teste a rodar depois de instalar, porque valida a chave da Anthropic.
- **`bash tests/run_all.sh`**: bateria completa sem internet (precisa de Python, Node e Playwright com Chromium). Ela roda (8 etapas): verificações estáticas (painel x servidor x prompts x `.env`), o ciclo automático da fila, o conector do WhatsApp ligado ao servidor (com bibliotecas simuladas) e os avisos, a retomada e o funil (simulados), custos, teste A/B, CRM/agenda e backup, o resumo diário e os conectores Pipedrive/HubSpot, vários números, e o painel num navegador de verdade (agentes, planilha, disparo, fila, QR, arquivos, áudio, SAIR).
- O WhatsApp, o Claude e o Whisper são simulados nesses testes. Eles não substituem o teste com a sua conta: conexão do QR com um número real, resposta real do Claude e envio real.

## Avisos ao corretor, retomada automática e funil
Três recursos para transformar conversa em venda (abas **Avisos**, **Retomada** e **Funil** do painel).

**Avisos ao corretor.** Quando o agente encaminha um lead, o lead pede atendente, uma reunião é marcada ou o lead responde e ninguém atendeu, a equipe é avisada pelos canais ligados:
- **WhatsApp**: informe o(s) número(s) na aba Avisos; o aviso sai pelo número conectado. No modo QR, o número do corretor deve já ter conversado com o número conectado (ou tê-lo nos contatos).
- **E-mail** e **Slack/Discord/Teams**: configurados no `.env` (`NOTIFY_EMAIL_TO`, `SMTP_*`, `NOTIFY_WEBHOOK_URL`; `PUBLIC_URL` coloca o link do painel no aviso).
- **Lembrete (SLA):** se ninguém marcar o lead como atendido em X minutos, o aviso se repete até o máximo definido, só no horário configurado. Marcar "atendido", assumir a conversa, mandar mensagem pelo painel ou registrar um resultado encerra os lembretes.
- Leads de teste nunca geram aviso. Há um botão para enviar um aviso de teste.

**Retomada automática.** Leads que pararam de responder (agente falou por último) recebem até 5 retomadas, nos prazos que você definir (padrão 24 h, 48 h, 96 h). Cada etapa pode ser escrita pelo Claude com base na conversa e na base de conhecimento, ou ser um texto fixo. As mensagens entram na mesma fila de envio (ritmo, limite diário, janela de horário e pausa automática valem), sempre trazem a opção SAIR, e qualquer resposta do lead reinicia o ciclo. Após a última etapa o lead vai para "sem resposta". Cada nicho pode desligar a retomada (caixa na aba Agentes). **API oficial:** fora da janela de 24 h só sai com template aprovado; informe o nome do template em cada etapa, senão a etapa é pulada (veja `templates_meta.md`).

**Funil de conversão.** Leads, responderam, qualificados, encaminhados e ganhos, com percentuais, tempos medianos (1ª resposta, até qualificar, até o corretor atender), quebra por nicho, série diária e efetividade das retomadas. "Ganho", "Perdido" e "Cotação enviada" são marcados por você em cada lead (botões na aba Conversas): o sistema não sabe sozinho se a venda fechou. Leads de teste não entram.

## Custos, teste A/B, CRM/agenda e backup
**Custos (aba Custos).** Cada chamada ao Claude registra tokens (entrada, saída e cache) e o custo estimado em R$. A tela mostra o gasto do período e do mês, a projeção, o custo por lead, por qualificado, por encaminhado e por venda, e a divisão por tipo de chamada e por nicho. Você define os preços (US$ por milhão de tokens), o dólar e um **orçamento mensal**: ao chegar em 80% e 100% o time é avisado (canais da aba Avisos) e, se escolher "parar de responder", a IA para até o próximo mês (as mensagens dos leads continuam salvas). Os preços padrão são só um ponto de partida; confira os do seu modelo no site da Anthropic. Os valores são estimativas, não a fatura.

**Teste A/B de prompts (aba Agentes > Teste A/B).** Escreva uma versão B do prompt e defina quantos % dos leads novos a usam. Cada lead fica sempre na mesma versão. "Ver resultados" compara A e B (leads, responderam, qualificados, encaminhados, ganhos, mensagens do lead e custo por lead) e diz se a diferença é estatisticamente relevante (teste z, p<0,05). Com menos de 30 leads por versão o painel pede para continuar o teste. Não edite o prompt B no meio do teste. O 1º contato é o mesmo nas duas versões. "Testar com prompt B" cria um lead de teste na versão B.

**CRM e agenda (aba Integrações).** O sistema envia eventos (qualificado, encaminhado, reunião agendada, pediu atendente, descartado, sem resposta, cotação enviada, ganho, perdido) por webhook, em JSON assinado (cabeçalho `X-SDR-Signature: sha256=...`, HMAC-SHA256 do corpo com o seu segredo), com até 3 tentativas. Serve para n8n, Make, Zapier ou qualquer CRM que aceite webhook. Há também conectores prontos para **Pipedrive** e **HubSpot** (veja abaixo). Também há exportação de leads em CSV (separador `;`, abre no Excel; fórmulas são neutralizadas) e, para reuniões agendadas, arquivo `.ics` e atalho do Google Agenda no lead. O agente registra a reunião como `AAAA-MM-DD HH:MM` (horário de Brasília); se ele escrever a data de outro jeito, o `.ics` não é gerado.

**Cópia externa do backup (Supabase).** O backup diário também é enviado a um bucket privado do Supabase Storage, para sobreviver à perda do servidor. Guia: **SUPABASE.md**.

**Backup e hospedagem.** Backup diário automático (banco + arquivos recebidos) e botão "Fazer backup agora" na aba Integrações; restauração com `python restore_backup.py arquivo.zip`. `/health` para monitoramento. Para colocar no ar com HTTPS, veja **HOSPEDAGEM.md** (Docker + Caddy).

## Hospedar para clientes e cobrar mensalidade
A pasta `deploy/` traz o kit do operador (`sdr-admin.py`): cria uma instância separada por cliente (API oficial ou QR, à escolha de cada um), controla vencimento da assinatura (suspende quem não pagou, reativa ao renovar) e gera os arquivos do Docker e do HTTPS. Há também o **receptor de pagamentos** (`sdr-cobranca.py`: Asaas, Stripe ou HMAC genérico renovam sozinhos), o **painel do operador**, **avisos graduais** de vencimento no painel do cliente e **tolerância** por cliente antes de suspender. Leia `deploy/GUIA-OPERADOR.md` (inclui riscos, LGPD e cobrança) e `deploy/termos-modelo.md` (esqueleto para um advogado revisar).

## Regras de proteção embutidas
- **Aceite do risco do QR:** no modo QR nada é enviado até alguém aceitar, no painel, o aviso de risco de banimento (grava quem/quando/versão).
- **Consentimento:** todo disparo exige a **origem do consentimento** (ex.: "formulário do site, 12/10"), gravada em cada lead.
- **Supressão:** quem escreve SAIR (ou é descartado) entra numa lista de supressão (só hash) e não recebe disparo nem por reimportação.
- **LGPD:** na aba LGPD, exportar os dados de um lead (JSON) e apagar (mantém só a supressão, se houver). O registro de pedidos não guarda telefones.
- **Aviso do operador:** faixa no topo do painel com vencimento próximo/vencido (veja `deploy/GUIA-OPERADOR.md`).
Isto ajuda a cumprir regras, mas não substitui um advogado: contrato, política de privacidade e papéis de controlador/operador precisam de revisão jurídica.

## Vender pelo WhatsApp: catálogo, pagamento e avaliação
Três recursos que transformam o agente de "qualifica e passa adiante" em "responde com dados certos, fecha e é medido".

**1. Catálogo e base de conhecimento (aba Agentes, por nicho).**
- *Catálogo:* produtos com preço, unidade, descrição, desconto máximo e link de pagamento fixo (opcional). Cadastre um a um ou cole uma lista (`nome;preço;descrição;link;desconto_max;unidade`). **O preço que o agente fala é sempre o do cadastro**, e as regras de venda mandam ele não inventar preço, prazo nem desconto.
- *Documentos:* FAQ, políticas, condições, argumentos. Base pequena (até ~6 mil caracteres, ajustável com `KB_BUDGET_CHARS`) vai inteira no prompt; base grande entra só nos **trechos que combinam com a conversa** (busca por palavras, sem custo de IA, ignora acento e plural). Aceita texto colado ou arquivo .txt/.md/.csv; para PDF/Word, copie e cole.
- O botão **Ver** mostra exatamente o que o agente enxergaria para uma pergunta, para você conferir antes de ir ao ar.
- Duplicar o nicho copia catálogo e documentos; excluir o nicho apaga os dois.

**2. Fechamento com link de pagamento (aba Integrações > Pagamentos).** O agente ganha a ferramenta `gerar_link_pagamento` quando há produto vendável e a cobrança está configurada. Ele informa só **produto, quantidade e desconto pedido**; o sistema calcula o total pelo cadastro, **recusa desconto acima do máximo** (devolve "ofereça o máximo ou chame um humano") e cria o link. Três modos:
- *Link fixo:* usa o link cadastrado no produto (Mercado Pago, Kiwify, Hotmart...). Sem desconto. O provedor não avisa o sistema, então você dá baixa em **Funil > Vendas > marcar pago**.
- *Asaas:* link gerado na hora (valor exato, validade configurável). O webhook do Asaas (URL e token mostrados na tela) dá baixa sozinho.
- *Stripe:* sessão de checkout gerada na hora; o webhook (com assinatura verificada, rejeita eventos com mais de 5 minutos) dá baixa sozinho.
Pagamento confirmado: pedido vira *pago*, o lead vira **ganho** (e segue para o CRM), a equipe recebe o aviso "Venda confirmada" e o cliente recebe a mensagem de confirmação (editável; vazio desliga). Valor pago menor que o pedido **não** fecha a venda. Eventos repetidos são ignorados. Pedido repetido nas últimas 6 h devolve o mesmo link. Em **Funil > Vendas** você vê pedidos, receita e conversão link→pago.
Limites honestos: as chamadas ao Asaas e ao Stripe seguem a documentação, mas **foram testadas só com servidores simulados**; faça um pagamento de teste no sandbox antes de vender. Cancelar um pedido no painel não cancela o link no provedor. Se o provedor falhar, o agente avisa o cliente e chama um humano.

**3. Avaliação com clientes simulados (aba Agentes > Avaliar o agente).** Um segundo Claude faz o papel de clientes difíceis: decidido, pechincheiro, curioso frio, pergunta fora da base, desconfiado, que tenta quebrar as regras, que pergunta se é robô e que pede SAIR. Escolha os cenários e o número de mensagens; a tela mostra a **estimativa de custo** e pede confirmação (usa o Claude de verdade; aparece como "avaliacao" na aba Custos). Nada vai ao WhatsApp e os dados simulados são apagados ao final. O que é conferido:
- *Regras rígidas (falha grave, derrubam a nota em 30 pontos cada):* valor citado que não está no cadastro, link que o sistema não gerou, desconto acima do máximo, campo [ASSIM] na mensagem, vazamento de instruções internas, continuar falando depois do SAIR, negar ser assistente virtual quando perguntado. Mensagem longa demais é só aviso.
- *Juiz (notas de 1 a 5):* precisão, qualificação, tom, condução e fechamento, com a lista de erros e a conversa completa para você ler.
- A tela compara com a avaliação anterior e marca como **desatualizada** a que foi feita antes de você mudar prompt, base ou catálogo. A nota varia um pouco de uma execução para outra (o cliente simulado e o juiz também são IA): olhe tendências e as falhas graves, não décimos.
- Rode a avaliação sempre que mudar o prompt, a base ou o catálogo. Ela reduz o risco de o agente errar, mas **não o elimina**: continue lendo conversas reais no começo.

## Antes do primeiro disparo: preencha os campos [ASSIM]
Os nichos de exemplo trazem campos entre colchetes, como `[CORRETORA]`, `[NÚMERO]`, `[PRAZO]`, `[NOME]` e `[EMPRESA]`, no prompt e na mensagem de abertura. Se ficassem assim, o agente diria "[CORRETORA]" ao lead. Por isso o sistema **recusa o disparo** enquanto houver campos desse tipo no nicho (a mensagem de erro lista quais) e não envia itens antigos da fila nessa situação. Edite o nicho na aba Agentes e salve. Todo texto de abertura ganha automaticamente "responda SAIR" se você esquecer de incluir.

## Resumo diário, Pipedrive e HubSpot
**Resumo diário ao gestor (aba Avisos).** Num horário que você escolhe (opcionalmente só em dias úteis), o sistema manda um resumo do dia: leads novos, quantos responderam, qualificados, encaminhados, ganhos, saídas, quem está aguardando atendimento (com o tempo de espera) e o custo do Claude. Sai pelos mesmos canais dos avisos (WhatsApp, e-mail, webhook). Há botão de prévia e de envio de teste. Se você ligar depois do horário do dia, o primeiro resumo sai no dia seguinte.

**Pipedrive e HubSpot (aba Integrações).** Escolha o destino e informe as credenciais (o painel nunca devolve o token depois de salvo; deixe o campo em branco para mantê-lo):
- **Pipedrive:** domínio da conta (`minhaempresa` ou `minhaempresa.pipedrive.com`) e o token de API (Preferências pessoais > API). Cada lead vira uma *pessoa* e um *negócio*; as etapas do funil movem o negócio (ganho/perdido fecham), notas guardam o resumo do agente e reunião agendada vira atividade.
- **HubSpot:** token de um *Private App* com permissão de contatos, negócios e notas. Cada lead vira um *contato* e um *negócio* no funil padrão (as etapas usadas são as padrão da HubSpot: se o seu funil tem outros nomes, use o webhook).
- O botão **Testar conexão** valida o token sem criar nada. Falhas temporárias (429/5xx) são repetidas; o resultado de cada envio aparece no registro da aba.
- Os conectores foram testados contra servidores simulados que seguem a documentação das duas APIs; **teste com uma conta de verdade (de preferência uma de teste) antes de confiar**, porque campos personalizados e funis customizados mudam de conta para conta.

## Vários números (modo QR)
Em **Envio e conexão** você pode cadastrar mais de um número (até `LINES_MAX`, padrão 5) com **Adicionar número**. Cada um é uma sessão separada do gateway, com QR e código próprios:
- **Ritmo por número:** intervalo, pausa de lote, **limite diário e aquecimento são de cada número** (o número novo começa em 20 por dia mesmo que o antigo já esteja em 80). O limite do dia mostrado no topo é a soma dos números ativos.
- **Distribuição:** num disparo você escolhe o número ou deixa em *Automático*, que divide a fila entre os números conectados (o que enviou menos no dia vai primeiro). Se o número escolhido estiver desconectado, os contatos esperam por ele: não passam para outro sem você pedir.
- **Conversa continua no mesmo número:** quem responde a um número é atendido por ele; retomadas saem pelo número com que o lead conversou. Se o lead passar a falar com outro número seu, a conversa segue por esse.
- **Avisos internos** (corretor/gestor) saem pelo primeiro número conectado, começando pelo principal.
- **Falhas:** 3 falhas seguidas num número com outros ativos põem só ele em espera por 30 min; com um número só, vale a pausa automática de sempre. A pausa por excesso de saídas/descartes continua geral.
- Dá para pausar/reativar um número, e remover (encerra a sessão dele; os contatos na fila dele são redistribuídos). O número principal não pode ser removido.
- **Importante:** mais números **não** tornam o envio mais seguro. O risco de bloqueio é de cada número e o WhatsApp avalia o comportamento (denúncias, bloqueios, mensagens para quem não conhece você). Use vários números para dividir o atendimento de contatos que deram consentimento, não para contornar limites; manter volumes baixos, consentimento e a opção SAIR continua sendo o que protege. Cada número precisa estar no seu nome ou ter autorização do titular.
- Na API oficial da Meta há um número por configuração; este recurso só vale com `PROVIDER=qr`.

## Usar o painel
1. **Agentes (nichos):** edite o prompt, o 1º contato e as palavras-chave, salve, e teste nos dois modos. **Testar ativo** cria um lead que já recebeu o 1º contato; **Testar receptivo** cria um lead que ainda não falou com ninguém, e você escreve primeiro como cliente. Nada é enviado ao WhatsApp e o CRM e o log aparecem ao vivo.
2. **Disparar:** em Conversas, clique em Disparar, escolha o **nicho de atuação**, cole os contatos (`telefone;nome;empresa`, um por linha) e confirme o consentimento. Um contato é enviado na hora; vários entram numa fila com intervalo entre mensagens (`BULK_DELAY_MIN/MAX`, padrão 3 a 8 s).
3. **Acompanhar:** lista de leads com estágio e nicho, chat, cartão do CRM (os campos mudam conforme o nicho) e log de eventos. **Assumir conversa** pausa a IA para você responder.

Pular automaticamente: leads que pediram para sair e leads que já estão em conversa.

## Conectar por QR code (modo WhatsApp Web) e ritmo de envio
Além da API oficial, dá para conectar um número escaneando o QR code, como no WhatsApp Web. Isso usa a pasta `gateway/` (Node.js + biblioteca não oficial Baileys).

**Aviso importante:** o modo QR não é suportado pela Meta, pode violar os Termos do WhatsApp e o número pode ser bloqueado, mesmo com todos os limites abaixo. Para volume e segurança, a API oficial é o caminho recomendado. Use um número que você aceite perder, só com quem consentiu, e mantenha o SAIR.

1. No `.env` do servidor: `PROVIDER=qr` e `GATEWAY_SECRET=<senha longa>`.
2. Em outro terminal:
```bash
cd gateway
npm install
GATEWAY_SECRET=<a mesma senha> npm start
```
3. Abra o painel > **Envio e conexão**. Aparece o QR code: no celular, WhatsApp > Aparelhos conectados > Conectar um aparelho. A sessão fica salva em `gateway/auth/` (guarde com segurança, equivale à sua conta).
4. O gateway só escuta em 127.0.0.1. Rode servidor e gateway na mesma máquina e não exponha a porta 3001.

**Sem conseguir usar a câmera? Conecte pelo número (sem QR):** no painel, em Envio e conexão, digite o número da conta (DDI + DDD) e clique em **Gerar código**. No celular: WhatsApp > Aparelhos conectados > Conectar um aparelho > **Conectar com número de telefone**, e digite o código de 8 caracteres. Só aparece enquanto o gateway estiver aguardando o QR.

**O QR não conecta? Confira nesta ordem:**
1. Escaneie pelo leitor **dentro do WhatsApp** (Configurações > Aparelhos conectados > Conectar um aparelho), não pela câmera do celular. No WhatsApp Business, é o mesmo caminho.
2. O QR vale cerca de 20 segundos e renova sozinho. Se demorar, espere o próximo. Em tela escura, aumente o brilho; o QR agora tem borda branca e 280 px. Alternativa: abra `http://127.0.0.1:3001/qr?key=SUA_SENHA` (QR grande e atualizado a cada 2 s) ou escaneie o QR que aparece no terminal do gateway.
3. Veja o terminal do gateway: ele mostra `[conexão]` e o código do erro. **405:** biblioteca desatualizada, rode `npm update @whiskeysockets/baileys` e reinicie. **440:** há outro gateway aberto com a mesma conta. **515:** é normal logo após escanear (ele reconecta sozinho).
4. A conta permite até 4 aparelhos conectados. Se já estiver no limite, remova um em Aparelhos conectados.
5. O celular precisa de internet e a hora do celular e do servidor devem estar corretas. O servidor precisa alcançar os servidores do WhatsApp (firewall e VPN podem bloquear).
6. Se aparecer "não é possível conectar novos dispositivos agora", é uma limitação temporária da conta no WhatsApp: tente de novo mais tarde.
7. Para recomeçar do zero: pare o gateway, apague as pastas `gateway/auth/` e `gateway/auth-*` (números extras) e o arquivo `gateway/lines.json`, e inicie de novo.

**O que o ritmo de envio faz (aba Envio e conexão, vale para os dois modos):**
- Todo disparo ativo vira uma **fila**. O sistema envia um contato por vez, com intervalo aleatório entre o mínimo e o máximo configurados, mais uma pausa ocasional maior.
- **Pausa de lote:** depois de N envios (N varia um pouco), espera vários minutos.
- **Limite diário** e **aquecimento**: começa em 20 contatos novos por dia e sobe 10 por dia até o limite (padrão 80, teto 300).
- **Janela de envio** (padrão 9h às 18h, dias úteis, fuso America/Sao_Paulo).
- **Atraso humano nas respostas:** o agente espera alguns segundos e mostra "digitando" antes de responder (também no modo QR para o 1º contato).
- No modo QR, confere se o número tem WhatsApp antes de enviar e pula os que não têm.
- **Pausa automática** se houver 3 falhas de envio seguidas (com vários números, só o número com falha descansa) ou se os pedidos de sair/descartes passarem do limite (padrão 8% nos últimos 7 dias, com pelo menos 20 envios). O painel mostra o motivo e você decide quando retomar.
- **Métricas:** enviados hoje e limite, fila, falhas, taxa de resposta, taxa de saída/descarte, intervalo médio, envios por hora, resultado por nicho e um indicador de risco (baixo, médio, alto). O indicador é uma estimativa interna e não garante nada.

## Ligar ao WhatsApp real (API oficial)
1. Em developers.facebook.com, crie um app Business com o produto **WhatsApp**; anote o **Phone number ID** e gere um token (em produção, token permanente de um System User).
2. Preencha `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `VERIFY_TOKEN` e `META_APP_SECRET` no `.env`.
3. Publique o servidor em HTTPS (Render, Railway, Fly.io, VPS; para teste, `cloudflared` ou `ngrok`). Com SQLite em nuvem, use disco persistente.
4. Na Meta, em WhatsApp > Configuração > Webhook, use `https://SEU-DOMINIO/webhook` com o mesmo `VERIFY_TOKEN` e assine o campo **messages**.
5. Para cada nicho que faz prospecção ativa, aprove um **template** (1 variável `{{1}}` = primeiro nome; veja `templates_meta.md`) e informe o nome no editor do nicho. Sem template, texto livre só chega a quem falou com você nas últimas 24h.

## Pontos para você completar
- **Atualizar o agente de saúde que já está no banco:** o arquivo `sdr_prompt.txt` e a base `sdr_knowledge.md` só são lidos na primeira execução. Para um sistema já em uso, abra Agentes > Planos de saúde e use **Carregar de arquivo** em cada campo (prompt e base de conhecimento), depois **Salvar**.
- `server.py`, função `exec_tool`: `TODO` para integrar o CRM real, a agenda e a notificação do vendedor.
- Prompts: preencha os trechos entre colchetes ([EMPRESA], operadoras, preços de referência etc.).

## Cuidados
- Só dispare para quem consentiu ou tem base legal (LGPD). O painel exige a confirmação e registra no log. SAIR/PARAR descarta o lead.
- Mantenha `DASH_TOKEN` forte: o painel mostra conversas de clientes.
- No nicho de saúde, revise o prompt com seu jurídico/compliance. Revise as conversas no início antes de escalar o volume.
