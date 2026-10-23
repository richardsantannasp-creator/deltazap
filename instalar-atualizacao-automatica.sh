#!/usr/bin/env bash
# Liga (ou desliga) a atualização automática do SDR. Rode UMA vez no servidor, como root, dentro da pasta do projeto:
#   cd /opt/sdr && sudo ./instalar-atualizacao-automatica.sh           (liga: todo dia às 04:15, horário do servidor)
#   cd /opt/sdr && sudo ./instalar-atualizacao-automatica.sh --remover (desliga)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Rode como root (sudo)."; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"
ARQ=/etc/cron.d/sdr-atualizar
if [ "${1:-}" = "--remover" ]; then rm -f "$ARQ"; echo "Atualização automática desligada."; exit 0; fi
command -v flock >/dev/null || { echo "Falta o comando flock (apt install util-linux)."; exit 1; }
chmod +x "$DIR/atualizar-docker.sh"
cat > "$ARQ" <<CRON
# Atualização automática do SDR (instalada por instalar-atualizacao-automatica.sh)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
15 4 * * * root cd $DIR && ./atualizar-docker.sh >> /var/log/sdr-atualizacao.log 2>&1
CRON
chmod 644 "$ARQ"
echo "Ligado: todo dia às 04:15 (horário do servidor) o sistema procura versão nova, atualiza e confere."
echo "Acompanhar:  tail -f /var/log/sdr-atualizacao.log"
echo "Testar agora: cd $DIR && ./atualizar-docker.sh"
echo "Desligar:     sudo $DIR/instalar-atualizacao-automatica.sh --remover"
