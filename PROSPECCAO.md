# Prospecção por Google (aba "Prospecção")

Busca empresas por nicho e cidade na **API oficial do Google Places**, procura o WhatsApp que a própria empresa divulga no site e manda as escolhidas para a **fila normal do SDR**.

## Ligar
1. No Google Cloud: crie um projeto, ative **Places API (New)**, crie uma chave e **restrinja-a** à Places API. Defina também uma cota diária (proteção do seu bolso).
2. No servidor: `nano /opt/sdr/.env` e acrescente `GOOGLE_PLACES_API_KEY=sua_chave`. Depois `cd /opt/sdr && docker compose up -d --build`.
3. Painel → **Prospecção**.

## Como usar
1. Nicho (ou vários, separados por `;`) + cidade → **Buscar empresas**. *Rápido* traz até 60 por nicho; *Cobertura total* divide a cidade em quadrantes (use o limite de chamadas para controlar o custo; cada 20 empresas = 1 chamada).
2. A lista mostra o WhatsApp e a origem: **Site da empresa** (ela mesma divulga: confiável) ou **provável celular** (só o formato do número: pode não ter WhatsApp).
3. **Marcar confirmados** seleciona os de WhatsApp confirmado (até 100 por vez), escolha o agente e o número de envio, marque a confirmação e **Enfileirar**.
4. Os envios seguem o ritmo, o limite diário, o aquecimento de 14 dias, a janela de horário e a lista de supressão. Quem responder SAIR (ou marcado "Não contatar") nunca mais recebe e some das exportações.

## O que o sistema faz por você (e o que continua sendo seu)
- Cada item da fila grava a origem: "Prospecção B2B — Google Places, data… base legal: legítimo interesse". Fica no histórico de ações e no registro LGPD.
- Nada é enviado sem você marcar a confirmação; o sistema nunca dispara sozinho após a busca.
- **Atenção:** estas empresas **não deram opt-in**. Abordagem B2B por legítimo interesse (LGPD) exige mensagem breve, identificação clara e opção de sair, e o WhatsApp pode bloquear números que recebem muita denúncia. Comece com poucos por dia, só com "confirmado no site", e acompanhe o painel de saúde da linha. A decisão e o risco do número são do operador.
- Termos do Google: os dados das buscas ficam guardados por **30 dias**; empresas que não foram para a fila são apagadas depois disso (quem virou lead permanece como lead).
- Os sites das empresas são lidos só quando são endereços públicos (endereços internos são recusados).
