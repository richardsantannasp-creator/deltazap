# Começar a usar o sistema de verdade (passo a passo)

A página de "prévia" que aparece no Claude é só uma demonstração com dados fictícios: o QR dela é um desenho e não conecta ao WhatsApp. Para conectar um número de verdade, o sistema precisa rodar no seu computador (ou em um servidor).

## O que instalar (uma vez)
- Python 3.10 ou mais novo: https://www.python.org/downloads/ (no Windows, marque "Add Python to PATH")
- Node.js 20 (LTS): https://nodejs.org/

## 1. Configurar
Abra um terminal na pasta `sdr-whatsapp` (no Windows: PowerShell).

Windows:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy env.example .env
```
Mac/Linux:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env
```
Abra o arquivo `.env` em um editor de texto e preencha:
```
ANTHROPIC_API_KEY=sua-chave-da-anthropic
DASH_TOKEN=uma-senha-sua-para-o-painel
PROVIDER=qr
GATEWAY_SECRET=outra-senha-longa-qualquer
```

## 2. Ligar o servidor (terminal 1)
```
uvicorn server:app --port 8000
```

## 3. Ligar o conector do WhatsApp (terminal 2, outra janela)
```
cd gateway
npm install
npm start
```
O conector lê a senha `GATEWAY_SECRET` do mesmo arquivo `.env`, então não precisa digitar nada. O QR aparece também no próprio terminal.

## 4. Conectar o número
1. No navegador, abra **http://localhost:8000** (não o link da prévia do Claude).
2. Digite o `DASH_TOKEN` quando pedir.
3. Abra a aba **Envio e conexão**. O QR e o botão **Gerar código** agora são de verdade.
4. No celular: WhatsApp > Aparelhos conectados > Conectar um aparelho. Escaneie o QR, ou toque em "Conectar com número de telefone" e digite o código gerado.

Para usar mais de um número: nessa mesma aba, digite um nome em **Adicionar número**, clique no botão e escaneie o novo QR com o outro celular. Cada número tem seu limite diário. Leia a seção "Vários números" do README antes (mais números não reduzem o risco de bloqueio).

Como saber que é o painel real: os números da aba Envio começam zerados e o aviso "PRÉVIA" não aparece.

## 5. Antes de disparar
Na aba **Agentes**, preencha no nicho tudo o que está entre colchetes (`[CORRETORA]`, `[PRAZO]` etc.) e revise a mensagem de abertura. Enquanto sobrar algum, o sistema não deixa disparar. Use "Testar ativo" para ver o 1º contato sem enviar nada ao WhatsApp.

## 5a. Verificar a instalação e fazer um piloto
Clique em **Verificar instalação** (topo do painel): ele confere chave do Claude, WhatsApp, áudio, vídeo, avisos, orçamento e backup, e diz o que corrigir. Depois siga o `PILOTO.md` (7 dias, com um número de teste) antes de divulgar ou vender.

## 5b. Para o agente vender de verdade (recomendado antes de divulgar)
1. Aba **Agentes** > *Catálogo*: cadastre seus produtos com preço e desconto máximo. Em *Documentos*: cole FAQ, prazos, condições.
2. Aba **Integrações** > *Pagamentos*: escolha link fixo, Asaas ou Stripe (comece pelo sandbox/teste).
3. Aba **Agentes** > *Avaliar o agente*: rode a avaliação (mostra o custo antes), leia as falhas graves e ajuste o prompt/base até zerá-las.
4. Acompanhe pedidos e receita em **Funil > Vendas**. Detalhes no README, seção "Vender pelo WhatsApp".

## 5c. Ter pessoas atendendo junto com a IA (opcional)
Na aba **Avisos**, em **Equipe de atendimento**, cadastre cada atendente (nome, usuário e senha). Eles entram em `http://localhost:8000/atendente` (ou `https://SEU-DOMINIO/atendente` em produção), ficam *disponíveis* e recebem as conversas que a IA transfere, ou que você envia com **Enviar à equipe**. Se ninguém estiver disponível, a conversa espera na fila. Detalhes no README, seção "Transferência para atendente humano".

Se quiser que alguém tenha **o próprio número de WhatsApp e a própria equipe**, crie um **gestor** em **Avisos > Gestores de equipe**. Ele entra em `/gestor` e só vê o que é dele (veja `GESTOR.md`).

## 5d. Materiais, horário da equipe e Google Agenda (opcional)

- **Materiais** (catálogo em PDF, vídeo, imagem): Agentes > seu nicho > "Materiais para enviar". O agente envia sozinho quando o lead pede.
- **Horário da equipe, respostas rápidas, notas e desempenho**: aba Avisos > Equipe de atendimento.
- **Google Agenda de verdade**: siga o **AGENDA-GOOGLE.md** (10 minutos) e use Integrações > Google Agenda > Testar conexão.
- Na API oficial da Meta, depois de 24 h sem resposta do lead só vai template aprovado; o sistema avisa quando a mensagem não pôde ser enviada.

## Se algo falhar
- O painel diz "gateway offline": o terminal 2 não está rodando.
- "Defina GATEWAY_SECRET" no terminal 2: o `.env` precisa estar na pasta `sdr-whatsapp` (uma pasta acima de `gateway`) e ter a linha `GATEWAY_SECRET=...`.
- Outros problemas de QR: veja a seção "O QR não conecta?" do README.md.


## Novidades: avisar o corretor, retomada e funil
- Aba **Avisos**: coloque o WhatsApp do corretor e clique em "Enviar aviso de teste". Ele passa a ser avisado a cada lead encaminhado e recebe lembretes se ninguém atender.
- Aba **Retomada**: ligue e ajuste os prazos. Leads que pararam de responder recebem mensagens de retomada pela fila (sempre com a opção SAIR).
- Aba **Funil**: veja quantos leads viram venda. Marque "Ganho" ou "Perdido" em cada lead (aba Conversas) para o funil ficar completo.
- E-mail e Slack/Discord são opcionais: preencha as variáveis de "Avisos para a equipe" no `.env`.

## Mais novidades: custos, A/B, CRM/agenda e backup
- **Custos:** acompanhe quanto o Claude está custando e defina um orçamento mensal.
- **Teste A/B:** em Agentes, escreva um prompt B e veja qual versão qualifica mais leads.
- **Integrações:** envie eventos ao seu CRM por webhook, exporte os leads em CSV e baixe as reuniões em .ics.
- **Backup:** automático todo dia; baixe pela aba Integrações. Para colocar num servidor com HTTPS, leia o HOSPEDAGEM.md.
