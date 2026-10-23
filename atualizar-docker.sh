#!/usr/bin/env bash
# Atualização automática do SDR (instalação com Docker): só age quando há versão nova no GitHub.
# Faz cópia do banco, baixa, reconstrói, confere /health por dentro do container e VOLTA à versão anterior se não subir.
# Uso: ./atualizar-docker.sh            (normal: não faz nada se já está na última versão)
#      ./atualizar-docker.sh --agora    (ignora a verificação de horário de envio)
# Não mexe em: .env, banco, anexos, backups nem na sessão do WhatsApp (ficam em volumes do Docker).
set -uo pipefail
cd "$(dirname "$0")"
BRANCH="${BRANCH:-main}"
say(){ echo "[$(date '+%F %T')] $*"; }
exec 9>/tmp/sdr-atualizar.lock; flock -n 9 || { say "outra atualização em andamento"; exit 0; }

git fetch -q origin "$BRANCH" || { say "sem acesso ao GitHub agora; nada alterado"; exit 0; }
ATUAL="$(git rev-parse HEAD)"; NOVA="$(git rev-parse "origin/$BRANCH")"
[ "$ATUAL" = "$NOVA" ] && exit 0                     # já está na última versão: silêncio

saudavel(){ for _ in $(seq 1 30); do docker compose exec -T sdr python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)" >/dev/null 2>&1 && return 0; sleep 3; done; return 1; }

say "versão nova ${NOVA:0:7} (atual ${ATUAL:0:7}): atualizando"
docker compose exec -T sdr sh -c 'mkdir -p /data/backups && cp /data/sdr.db "/data/backups/sdr-antes-atualizar-$(date +%s).db"' >/dev/null 2>&1 || say "aviso: não consegui copiar o banco antes (o backup diário continua valendo)"
git merge -q --ff-only "origin/$BRANCH" || { say "git não conseguiu atualizar (há mudanças locais no servidor?). Nada foi alterado."; exit 1; }
docker compose up -d --build >/dev/null 2>&1 || say "aviso: o docker compose reportou erro na reconstrução"
if saudavel; then
  docker image prune -f >/dev/null 2>&1
  say "OK: versão ${NOVA:0:7} no ar"
  exit 0
fi
say "FALHOU: o sistema não respondeu. Voltando para ${ATUAL:0:7}"
git reset -q --hard "$ATUAL"
docker compose up -d --build >/dev/null 2>&1
if saudavel; then say "versão anterior restaurada e no ar"; else say "NÃO consegui confirmar a volta: veja 'docker compose logs sdr'"; fi
exit 1
