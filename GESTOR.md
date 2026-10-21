# Gestor de equipe

Um **gestor** é uma pessoa de confiança (por exemplo, um líder de vendas ou um parceiro) que usa o seu sistema com **o próprio WhatsApp** e **a própria equipe**, sem ver nada do que é seu nem de outros gestores.

## O que o gestor faz
Entra em `https://SEU-DOMINIO/gestor` com usuário e senha e pode:
- **Meu WhatsApp:** conectar o número dele (QR code ou código), desconectar, renomear, remover.
- **Minha equipe:** criar atendentes (que entram em `/atendente`), trocar senha, desativar, excluir.
- **Conversas:** ver as conversas dos números dele, assumir, responder, devolver à IA, enviar à equipe dele.
- **Desempenho:** conversas atendidas, tempo de 1ª resposta, espera na fila, ganhos e perdidos da equipe dele.
- **Disparo e agenda:** coloca na fila contatos **dele** (lista colada ou planilha), sempre pelo número dele, e escolhe a agenda do Google onde as reuniões marcadas pela IA para os contatos dele vão cair.
- **Etiquetas e quadro:** etiqueta as conversas, filtra e arrasta o cartão pelas etapas do funil.
- **Histórico:** o que ele e a equipe dele fizeram.
- **Segurança:** liga a verificação em duas etapas do próprio login.

## O que ele NÃO vê nem faz
- Conversas, números, atendentes e métricas de outros gestores ou do administrador.
- Configurações (agentes de IA, chaves, backups, pagamento, agenda). Isso continua só com o administrador.
- Os números e a fila de outros. O disparo do gestor **só sai pelos números dele**, exige a confirmação de consentimento (opt-in) e a origem do consentimento (fica registrada em cada contato), pula quem pediu SAIR e segue o ritmo, os limites diários e a pausa definidos por você.

## Como o administrador cria o acesso
1. No painel (`DASH_TOKEN`), aba **Avisos > Gestores de equipe**.
2. Informe nome, usuário, senha (mínimo de 8 caracteres; vazio gera uma) e os **limites**: quantos números e quantos atendentes ele pode ter.
3. A senha aparece **uma única vez**. Passe ao gestor com o endereço `/gestor`.
4. Na mesma lista você ajusta limites, troca a senha, desativa ou exclui. Excluir **não apaga nada**: os números e atendentes dele passam para você.

## Disparo do gestor
1. Aba **Disparo e agenda**: escolha o nicho (a abertura da conversa é a do nicho; quem edita nichos é você), o número de envio, cole os contatos (`telefone;nome;empresa;contexto`) ou importe uma planilha (aceita o CSV do Facebook).
2. Informe de onde veio o consentimento e marque a confirmação. Sem isso o sistema recusa.
3. A fila dele aparece na própria aba, e ele pode limpar o que ainda não foi enviado. Você enxerga tudo em **Envio e conexão**.

## Agenda por gestor
Você configura uma vez o Google Agenda (conta de serviço, em `AGENDA-GOOGLE.md`). Cada gestor informa o **ID da agenda dele** e compartilha essa agenda com o e-mail da conta de serviço (a tela mostra o e-mail). A IA consulta os horários livres e cria o evento **na agenda do dono da conversa**; sem agenda própria, usa a sua. Dias, horários, antecedência e duração são os da sua configuração.

## Supervisor (somente leitura)
Em **Avisos > Gestores de equipe** escolha o perfil **Supervisor** ao criar o acesso. Ele entra em `/gestor`, **vê** conversas, desempenho, fila de disparo e histórico de **todas** as equipes, mas **não consegue** responder, assumir, etiquetar, mover de etapa, disparar nem alterar nada (o servidor recusa com 403, não é só a tela). Serve para dono, diretor comercial, auditoria e consultores.

## Verificação em duas etapas (2FA)
Atendentes, gestores e supervisores ligam em **Segurança** (botão no topo): digitam a chave no app autenticador (Google Authenticator, Microsoft Authenticator, Authy), confirmam com um código e recebem **8 códigos de recuperação** (cada um vale uma vez e não aparecem de novo). A partir daí o login pede senha **e** código. Um código usado não vale de novo, e erros contam no limite de tentativas. Se alguém perder o celular e os códigos, você libera em **Avisos** com **Liberar 2FA** (a pessoa é desconectada e pode ligar de novo). O acesso de administrador continua por `DASH_TOKEN`, que deve ser longo e secreto.

## Regras de funcionamento
- O dono de uma conversa é o dono do **número** em que ela acontece. Uma transferência feita pela IA em um número do gestor só vai para **atendentes daquele gestor**. Se ninguém dele estiver disponível, a conversa espera na fila dele (e, se você configurou "A IA volta a atender", a IA retoma depois do prazo).
- Os **números dos gestores nunca são usados nos seus disparos**: envios sem número definido saem só pelos seus números.
- Os avisos internos (alertas de lead quente, resumo diário) saem pelos seus números.
- O **aceite do risco do modo QR** é um só, feito por você no painel. Enquanto não for feito, nenhum número envia, inclusive os dos gestores.
- A IA, a base de conhecimento, os nichos e o horário de atendimento são **os da empresa** (os seus). O gestor não os altera.
- Quem tem a senha do gestor controla o número e a equipe dele: use uma senha própria e troque se ele sair.

## Cuidados
- Cada número conectado por QR tem o mesmo risco de bloqueio. Use chip secundário, ritmo de envio conservador e só fale com quem aceitou contato (LGPD).
- Você, como administrador, tem acesso a todas as conversas. Avise os gestores e a equipe disso e da política de privacidade.
- Limite de números no sistema: `LINES_MAX` no `.env` (padrão 5), somando o seu e os dos gestores.

## Ainda não existe
Nichos/IA próprios por gestor e cobrança separada por gestor.
