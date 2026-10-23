# Colocar o SDR no ar (servidor, HTTPS e backup)

Rodar no seu computador serve para testar. Para atender leads todos os dias, o sistema precisa ficar num servidor ligado 24 h, com endereço seguro (HTTPS). Este guia usa Docker, que é o caminho mais simples.

> **Importante:** os arquivos `Dockerfile`, `docker-compose.yml` e `Caddyfile` foram escritos e a sintaxe foi validada, mas **as imagens não puderam ser construídas no ambiente em que preparei o sistema** (sem Docker em execução). Faça o primeiro "subir" num horário tranquilo e confira os logs.

> **Vai hospedar para vários clientes e cobrar mensalidade?** Use o kit do operador em `deploy/` (uma instância isolada por cliente, vencimento e suspensão): veja `deploy/GUIA-OPERADOR.md`. O resto deste arquivo trata de uma instalação só.

## 1. O que você precisa
- Um servidor Linux (VPS) com 1 GB de RAM ou mais (2 GB se for usar transcrição de áudio local). Para ler vídeos, o ffmpeg precisa estar instalado; no Docker ele já vem. Qualquer provedor serve.
- Um domínio ou subdomínio (ex.: `sdr.suaempresa.com.br`) apontando para o IP do servidor (registro A).
- Docker e Docker Compose instalados no servidor.

## 2. Instalar
1. Envie a pasta `sdr-whatsapp` para o servidor (scp, git ou o painel do provedor).
2. Entre na pasta e crie o arquivo `.env`: `cp env.example .env`, depois edite.
3. Preencha, no mínimo: `ANTHROPIC_API_KEY`, `DASH_TOKEN` (senha longa), `GATEWAY_SECRET` (outra senha longa, só no modo QR), `PROVIDER` e `SDR_DOMAIN`.
4. Suba tudo: `docker compose up -d --build`
5. Abra `https://SEU-DOMINIO`, informe o `DASH_TOKEN`, vá em **Envio e conexão** e escaneie o QR code (modo QR).

O Caddy emite e renova o certificado HTTPS sozinho. As portas 80 e 443 precisam estar liberadas no firewall do provedor. **Não abra** as portas 8000 e 3001: elas ficam só na rede interna do Docker.

## 3. Onde ficam os dados
- `sdr-data` (volume): banco de dados, arquivos recebidos e backups.
- `wa-session` (volume): sessão do WhatsApp. Sem ela você precisaria escanear o QR de novo a cada atualização. Quem tiver esta pasta controla o número: não copie para qualquer lugar.

## Vários números
As sessões de todos os números ficam no volume `wa-session` (pastas `auth`, `auth-<id>` e o arquivo `lines.json`). Guarde esse volume como uma senha: quem o tem controla os números. O backup do painel **não** inclui essas sessões (de propósito); se perder o volume, é preciso escanear o QR de cada número de novo. O servidor recadastra no gateway os números que faltarem sozinho.

## 4. Backup
- O sistema faz **um backup por dia** (banco + arquivos recebidos) e guarda os 14 mais recentes (`BACKUP_KEEP`). Veja e baixe na aba **Integrações**.
- Isso protege contra erro, **não** contra a perda do servidor. Copie os backups para fora dele (por exemplo, um disco/objeto do provedor, ou baixe periodicamente pelo painel). Os backups têm dados pessoais de leads: mantenha acesso restrito (LGPD).
- **Restaurar:** pare o sistema (`docker compose stop sdr`), copie o `.zip` para o servidor e rode dentro do contêiner: `docker compose run --rm -v $(pwd):/in sdr python restore_backup.py /in/sdr-AAAAMMDD-HHMMSS.zip /data`, depois `docker compose up -d`. O banco anterior é guardado como `sdr.db.antes-da-restauracao-...`.
- Teste uma restauração uma vez, num servidor de teste, antes de precisar dela.

## 5. Atualizar o sistema
Substitua os arquivos (`server.py`, `dashboard.html`...) e rode `docker compose up -d --build`. Os volumes continuam, então nada se perde. Faça um backup antes.

## 6. Monitorar
- `GET https://SEU-DOMINIO/health` responde `{"ok": true, ...}` sem pedir senha e sem expor dados. Use em um monitor externo (UptimeRobot, Better Stack...) para ser avisado se cair.
- Logs: `docker compose logs -f sdr` e `docker compose logs -f gateway`.
- Os avisos de custo e de leads aguardando chegam pelos canais da aba **Avisos**.

## 7. Segurança em poucas linhas
- Use `DASH_TOKEN` longo e único; o painel só deve ser acessado por HTTPS.
- Mantenha o servidor atualizado (`apt upgrade`) e o acesso por chave SSH.
- O `.env` contém chaves: não versione nem envie por e-mail.
- Modo QR usa biblioteca não oficial e pode violar os Termos do WhatsApp: para operação comercial estável, prefira a API oficial (Meta Cloud API).

## Sem Docker (alternativa)
No servidor: `pip install -r requirements.txt`, `uvicorn server:app --host 127.0.0.1 --port 8000` e, na pasta `gateway`, `npm install && npm start`. Rode ambos como serviço (systemd) e coloque um Nginx ou Caddy na frente para o HTTPS.

## Atualização automática (Docker)

Uma vez, no servidor:

    cd /opt/sdr && sudo ./instalar-atualizacao-automatica.sh

Todo dia às 04:15 o sistema confere o GitHub; se há versão nova, copia o banco, atualiza, reconstrói e confere o `/health`
por dentro do container. Se não subir, volta sozinho à versão anterior. Sem versão nova, não faz nada.
Log: `tail -f /var/log/sdr-atualizacao.log` · Testar agora: `cd /opt/sdr && ./atualizar-docker.sh` · Desligar: `sudo ./instalar-atualizacao-automatica.sh --remover`.
