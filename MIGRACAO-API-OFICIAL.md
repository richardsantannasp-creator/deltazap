# Migração do QR para a API oficial do WhatsApp (Meta)

No painel: **Envio e conexão > API oficial do WhatsApp** mostra o que falta (✅ ok, ⚠️ atenção, ❌ falta), a qualidade do número, os templates prontos e o teste de envio. Nada ali muda o modo de envio.

## 1. Preparar a Meta
1. Business Manager verificado (CNPJ) em business.facebook.com.
2. App do tipo Business em developers.facebook.com com o produto **WhatsApp**.
3. Adicione o número. Ele não pode estar ativo no app do WhatsApp comum (apague a conta lá antes). **Não use o número do QR sem planejar isso.**
4. Crie um **usuário do sistema** e gere um **token permanente** (permissões `whatsapp_business_messaging` e `whatsapp_business_management`).
5. Anote: ID do número, ID da conta do WhatsApp Business (WABA) e a chave secreta do app.

## 2. Configurar o servidor (`/opt/sdr/.env`)
```
WHATSAPP_TOKEN=...
WHATSAPP_PHONE_ID=...
WHATSAPP_WABA_ID=...        # opcional: mostra o status dos templates no painel
META_APP_SECRET=...
VERIFY_TOKEN=uma-senha-longa-sua
```
Reinicie (`docker compose up -d --build`) e abra o painel: os itens vão ficando ✅. **Ainda com PROVIDER=qr**, nada muda no atendimento.

## 3. Webhook
Em WhatsApp > Configuração > Webhook: URL mostrada no painel (`https://seu-dominio/webhook`), o mesmo VERIFY_TOKEN, e assine **messages**. Quando a Meta chamar, o painel mostra "última chamada".

## 4. Templates
Os textos prontos (um por nicho + 3 de retomada) estão no painel. Crie no Gerenciador do WhatsApp (categoria Marketing, pt_BR, só a variável `{{1}}`). Depois de **Aprovado**, informe o nome em Agentes > nicho e na aba Retomada. Use o **teste de envio** com o seu número antes de ligar.

## 5. Transição sem perder nada
1. Mantenha o QR rodando enquanto os templates são aprovados.
2. Quando tudo estiver ✅, escolha um horário calmo, defina `PROVIDER=official` e reinicie.
3. Leads e histórico permanecem: o banco é o mesmo. O que muda: primeiro contato e retomadas só saem por template aprovado; dentro de 24 h da última resposta do lead a conversa é livre.
4. Para voltar ao QR, basta `PROVIDER=qr` e reiniciar.
5. Contatos sem opt-in (por exemplo vindos da Prospecção por Google) **não** devem ir para a API oficial: denúncias derrubam a qualidade do número (verde, amarelo, vermelho) e a Meta pode restringir a conta. Use a API oficial para quem deu consentimento.

## Qualidade do número
O painel mostra a classificação da Meta e o limite de mensagens por dia. Amarelo ou vermelho: reduza o volume, revise as aberturas e pare de enviar para listas frias.
