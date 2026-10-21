#!/usr/bin/env bash
# Prepara um servidor Ubuntu 24.04 (como o da Hostinger) para rodar o SDR: Docker, firewall e .env com senhas geradas.
# Rode UMA vez, como root, dentro da pasta do sistema:   sudo bash instalar-servidor.sh seu.dominio.com.br
set -euo pipefail
DOM="${1:-}"
[ "$(id -u)" -eq 0 ] || { echo "Rode como root (sudo bash instalar-servidor.sh dominio)"; exit 1; }
[ -n "$DOM" ] || { echo "Informe o domínio: bash instalar-servidor.sh sdr.suaempresa.com.br"; exit 1; }
cd "$(dirname "$0")"

echo "[1/4] atualizando o sistema e instalando o Docker"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get install -y ca-certificates curl git ufw unzip
command -v docker >/dev/null 2>&1 || curl -fsSL https://get.docker.com | sh

echo "[2/4] firewall: só SSH (22), HTTP (80) e HTTPS (443)"
ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

echo "[3/4] criando o .env"
if [ -f .env ]; then
  echo "  .env já existe: não foi alterado."
else
  cp env.example .env
  DASH="$(openssl rand -hex 16)"; GWS="$(openssl rand -hex 16)"
  sed -i "s|^DASH_TOKEN=.*|DASH_TOKEN=$DASH|; s|^GATEWAY_SECRET=.*|GATEWAY_SECRET=$GWS|" .env
  grep -q '^SDR_DOMAIN=' .env && sed -i "s|^SDR_DOMAIN=.*|SDR_DOMAIN=$DOM|" .env || echo "SDR_DOMAIN=$DOM" >> .env
  grep -q '^PROVIDER=' .env && sed -i "s|^PROVIDER=.*|PROVIDER=qr|" .env || echo "PROVIDER=qr" >> .env
  chmod 600 .env
  echo "  senha do painel (DASH_TOKEN): $DASH   <- anote agora"
fi

echo "[4/4] pronto. Falta você editar o .env (nano .env): ANTHROPIC_API_KEY e, se quiser, SUPABASE_*."
echo "Depois suba com:  docker compose up -d --build"
