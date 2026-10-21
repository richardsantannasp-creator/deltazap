#!/usr/bin/env bash
# Atualiza o SDR WhatsApp no servidor: backup, baixa a versão nova, reinicia, confere e volta atrás se falhar.
# Uso:  ./atualizar.sh                 (puxa a última versão do GitHub, branch main)
#       ./atualizar.sh arquivo.zip     (atualiza a partir de um zip)
# Variáveis opcionais: SERVICO_API (padrão sdr-api), SERVICO_GW (padrão sdr-gateway), PORTA (padrão 8000), BRANCH (padrão main)
# Não mexe em: .env, sdr.db, uploads/, backups/, sessão do WhatsApp (gateway/auth*), jids.json, lines.json.
set -uo pipefail
cd "$(dirname "$0")"
API="${SERVICO_API:-sdr-api}"; GW="${SERVICO_GW:-sdr-gateway}"; PORTA="${PORTA:-8000}"; BRANCH="${BRANCH:-main}"
STAMP="$(date +%Y%m%d-%H%M%S)"; BK="backups/codigo-$STAMP"; mkdir -p backups
say(){ echo "[atualizar] $*"; }

reiniciar(){
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q "^$API"; then
    sudo systemctl restart "$API"; systemctl list-unit-files | grep -q "^$GW" && sudo systemctl restart "$GW"
  elif command -v docker >/dev/null 2>&1 && [ -f docker-compose.yml ]; then
    docker compose up -d --build
  else
    say "Não achei systemd nem docker-compose: reinicie o servidor e o conector manualmente."; return 2
  fi
}
saudavel(){ for _ in $(seq 1 20); do curl -fsS "http://127.0.0.1:$PORTA/health" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }

say "1/5 backup do código atual em $BK"
mkdir -p "$BK"; tar --exclude=backups --exclude=node_modules --exclude=.venv --exclude=uploads --exclude='sdr.db*' --exclude='gateway/auth*' -cf - . | tar -xf - -C "$BK"
[ -f sdr.db ] && cp sdr.db "backups/sdr-antes-$STAMP.db"

say "2/5 baixando a versão nova"
if [ "${1:-}" != "" ]; then
  T="$(mktemp -d)"; unzip -q "$1" -d "$T" || { say "zip inválido"; exit 1; }
  SRC="$(find "$T" -maxdepth 2 -name server.py -printf '%h\n' | head -1)"; [ -n "$SRC" ] || { say "server.py não encontrado no zip"; exit 1; }
  rsync -a --exclude=.env --exclude='sdr.db*' --exclude=uploads --exclude=backups --exclude='gateway/auth*' --exclude=gateway/jids.json --exclude=gateway/lines.json --exclude=node_modules --exclude=.venv "$SRC"/ ./
else
  git fetch origin "$BRANCH" && git merge --ff-only "origin/$BRANCH" || { say "git não conseguiu atualizar (há mudanças locais?). Nada foi alterado."; exit 1; }
fi

say "3/5 dependências"
[ -d .venv ] && PIP=".venv/bin/pip" || PIP="pip"
$PIP install -q -r requirements.txt || say "aviso: pip falhou"
[ -d gateway ] && (cd gateway && npm install --omit=dev --silent || say "aviso: npm falhou")

say "4/5 reiniciando"
reiniciar; R=$?

say "5/5 conferindo (/health)"
if [ $R -eq 0 ] && saudavel; then say "OK: versão nova no ar. Backup do código anterior em $BK"; exit 0; fi
say "FALHOU. Voltando para a versão anterior..."
rsync -a "$BK"/ ./ && reiniciar && saudavel && say "Versão anterior restaurada e no ar." || say "Não consegui confirmar a volta: veja os logs do servidor."
exit 1
