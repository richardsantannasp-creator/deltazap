# Cópia externa do backup no Supabase

O sistema já faz um backup diário (banco, conversas, arquivos recebidos e materiais). Sozinho, ele fica **na mesma máquina** do servidor: se o servidor for perdido, o backup vai junto. Com o Supabase configurado, **cada backup também é enviado para um bucket privado** do Supabase Storage.

## Configurar (5 minutos)

1. No painel do Supabase (seu projeto), vá em **Storage > New bucket**. Nome: `sdr-backups`. **Deixe "Public bucket" desmarcado.** (Os backups têm dados pessoais de leads, protegidos pela LGPD.)
2. Vá em **Project Settings > API** e copie a chave **service_role** (a secreta, não a `anon`).
3. No `.env` do **servidor** (nunca no chat nem no GitHub), preencha:
   ```
   SUPABASE_URL=https://SEU-PROJETO.supabase.co
   SUPABASE_SERVICE_KEY=cole-a-chave-service_role-aqui
   SUPABASE_BUCKET=sdr-backups
   ```
4. Reinicie o servidor. No painel, aba **Integrações > Backup**, clique em **Testar cópia externa** e depois em **Enviar cópia agora**. O **Verificar instalação** passa a mostrar o último envio.

## Regras

- A chave `service_role` dá acesso total ao projeto Supabase. Guarde só no `.env` do servidor. Se vazar, gere outra em Project Settings > API.
- O sistema guarda os **30 backups mais recentes** no bucket (`OFFSITE_KEEP`); os mais antigos são apagados.
- O plano gratuito aceita arquivos de até **50 MB**. Se o backup passar disso, o painel avisa (os arquivos de leads crescem com o tempo): suba o plano ou reduza os anexos.
- Se o envio falhar, o backup local continua valendo e você é avisado por e-mail ou Slack/Discord (se configurados na aba Avisos).
- O painel avisa se o bucket estiver público.

## Restaurar a partir do Supabase

1. No Supabase: Storage > `sdr-backups` > baixe o `.zip` mais recente.
2. Copie para o servidor e siga a restauração do **HOSPEDAGEM.md** (`restore_backup.py`).

## O que ainda não é Supabase

O banco em uso continua SQLite no servidor (rápido e simples para um cliente por servidor). Trocar para Postgres do Supabase e o login do Supabase Auth são mudanças maiores, que só valem se você for rodar vários clientes num mesmo banco.
