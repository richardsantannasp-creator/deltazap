# Google Agenda: reunião marcada de verdade

Com isto ligado, o agente de IA **consulta os horários livres** da sua agenda, oferece 2 ou 3 ao lead e, quando o lead confirma, **cria o evento** (e apaga o antigo se o lead remarcar). Se o horário já estiver ocupado, for fora do expediente ou muito próximo, o agente não confirma e oferece outro.

Usa uma **conta de serviço** do Google (um "usuário robô"). Leva uns 10 minutos, uma única vez.

## Passo a passo

1. Acesse https://console.cloud.google.com e crie um projeto (ou use um existente).
2. Em **APIs e serviços > Biblioteca**, procure **Google Calendar API** e clique em **Ativar**.
3. Em **IAM e administrador > Contas de serviço**, clique em **Criar conta de serviço** (qualquer nome, ex.: `sdr-agenda`). Não precisa dar papéis.
4. Abra a conta criada > aba **Chaves** > **Adicionar chave > Criar nova chave > JSON**. Um arquivo `.json` é baixado. **Guarde-o como uma senha.**
5. No **Google Agenda** (calendar.google.com), abra as **configurações da agenda** que será usada (pode criar uma só para as reuniões do SDR):
   - **Compartilhar com pessoas específicas** > adicione o e-mail da conta de serviço (o `client_email` do JSON, algo como `sdr-agenda@projeto.iam.gserviceaccount.com`) com a permissão **Fazer alterações em eventos**.
   - Em **Integrar agenda**, copie o **ID da agenda**.
6. No painel, aba **Integrações > Google Agenda**: marque *Usar o Google Agenda*, cole o ID, cole o conteúdo do `.json`, ajuste duração, antecedência e os dias/horários em que a equipe recebe reuniões, e clique em **Salvar** e depois em **Testar conexão**. O teste mostra os próximos horários livres.

Alternativa para quem administra o servidor: `GOOGLE_SA_FILE=/caminho/chave.json` e `GOOGLE_CALENDAR_ID=...` no `.env` (o painel tem prioridade se também estiver preenchido).

## Como funciona e limites

- O sistema só **lê os períodos ocupados** (free/busy) e **cria/apaga os eventos que ele mesmo criou**. Não lê o conteúdo dos seus outros eventos.
- A chave privada fica só no servidor e nunca volta para a tela. O painel aceita apenas contas de serviço da Google (`oauth2.googleapis.com`).
- O evento leva o nome e o WhatsApp do lead na descrição. **Não há convite por e-mail ao lead**: contas de serviço não podem convidar participantes sem delegação de domínio do Google Workspace. A confirmação ao lead continua sendo pelo WhatsApp.
- Leads de **teste** nunca escrevem na agenda.
- Se o Google estiver fora do ar ou a agenda não estiver compartilhada, a reunião é registrada no painel como antes, a equipe é avisada e a IA diz ao lead que a equipe confirma o horário. O **Verificar instalação** mostra o erro com a instrução.
- Uma agenda para toda a empresa (não uma por vendedor). Mais de um vendedor com agendas separadas não está incluído.
