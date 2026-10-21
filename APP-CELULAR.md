# App no celular (atendentes e gestores)

Atendentes (`/atendente`) e gestores (`/gestor`) usam o sistema no celular como um **app instalado**, com **avisos** quando chega conversa, sem precisar de loja de aplicativos e sem deixar a aba aberta.

## O que o usuário faz (uma vez por aparelho)
**Android (Chrome):**
1. Abra `https://SEU-DOMINIO/atendente` (ou `/gestor`) e entre.
2. Menu do Chrome > **Instalar app** (ou "Adicionar à tela inicial").
3. Abra o app pelo ícone e toque em **Ativar avisos**; aceite a permissão.

**iPhone (iOS 16.4 ou mais novo, Safari):**
1. Abra o endereço no **Safari** e entre.
2. Toque em **Compartilhar** > **Adicionar à Tela de Início**.
3. Abra o app **pelo ícone da tela inicial** (não pelo Safari) e toque em **Ativar avisos**. No iPhone os avisos só funcionam com o app instalado.

**Computador:** funciona também: abra no Chrome ou Edge e toque em **Ativar avisos**.

## Quando chega aviso
- A IA transferiu uma conversa para o atendente.
- Há conversa **na fila** (os atendentes disponíveis da equipe e o gestor são avisados).
- O lead escreveu enquanto a conversa está com o atendente (ou com o gestor).
- Avisos seguidos do mesmo lead são agrupados (20 s) para não virar enxurrada.

## Privacidade
- O aviso mostra só "Nova mensagem" e o **primeiro nome** do lead. **Nunca** o texto da mensagem nem o telefone, porque a tela bloqueada pode ser vista por outros.
- Ao clicar em **Sair**, o aparelho deixa de receber avisos daquele usuário. Quem entra no mesmo aparelho depois passa a receber os dele.

## O que o administrador precisa saber
- Precisa de **HTTPS** (o domínio com Caddy já tem). Em `http://` o navegador não permite instalar nem receber avisos.
- As chaves dos avisos (padrão VAPID) são geradas sozinhas no primeiro uso e ficam no banco, e entram na cópia de segurança. Se você restaurar o sistema em outro servidor com o banco, os aparelhos continuam funcionando; se começar um banco novo, cada pessoa toca em **Ativar avisos** de novo.
- Opcional: `PUSH_CONTACT=voce@empresa.com` no `.env` (e-mail de contato exigido pelos serviços de aviso dos navegadores).
- O envio usa os serviços do próprio navegador (Google, Apple, Mozilla). Não há custo.
- Se um aparelho some (app desinstalado), o serviço avisa e o sistema remove a inscrição sozinho.

## Limites desta versão
- Avisos só quando o servidor sabe da conversa; não há "som contínuo" nem chamada.
- O painel do administrador (`/`) ainda não tem avisos no celular.
- O app abre o painel em tela cheia, mas precisa de internet (não funciona offline).
