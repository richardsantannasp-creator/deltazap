# Gestor de equipe

Um **gestor** é uma pessoa de confiança (por exemplo, um líder de vendas ou um parceiro) que usa o seu sistema com **o próprio WhatsApp** e **a própria equipe**, sem ver nada do que é seu nem de outros gestores.

## O que o gestor faz
Entra em `https://SEU-DOMINIO/gestor` com usuário e senha e pode:
- **Meu WhatsApp:** conectar o número dele (QR code ou código), desconectar, renomear, remover.
- **Minha equipe:** criar atendentes (que entram em `/atendente`), trocar senha, desativar, excluir.
- **Conversas:** ver as conversas dos números dele, assumir, responder, devolver à IA, enviar à equipe dele.
- **Desempenho:** conversas atendidas, tempo de 1ª resposta, espera na fila, ganhos e perdidos da equipe dele.

## O que ele NÃO vê nem faz
- Conversas, números, atendentes e métricas de outros gestores ou do administrador.
- Configurações (agentes de IA, chaves, backups, pagamento, agenda). Isso continua só com o administrador.
- Disparos ativos em massa. Nesta versão o gestor atende o que chega no número dele (receptivo) e as conversas transferidas.

## Como o administrador cria o acesso
1. No painel (`DASH_TOKEN`), aba **Avisos > Gestores de equipe**.
2. Informe nome, usuário, senha (mínimo de 8 caracteres; vazio gera uma) e os **limites**: quantos números e quantos atendentes ele pode ter.
3. A senha aparece **uma única vez**. Passe ao gestor com o endereço `/gestor`.
4. Na mesma lista você ajusta limites, troca a senha, desativa ou exclui. Excluir **não apaga nada**: os números e atendentes dele passam para você.

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
Gestor com disparo ativo próprio, agenda do Google por gestor, nichos/IA por gestor, e níveis intermediários (supervisor somente leitura).
