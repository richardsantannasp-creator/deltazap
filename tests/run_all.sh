#!/usr/bin/env bash
# Roda todos os testes que não precisam de internet nem de chaves (usa simulações de WhatsApp, Claude e Whisper).
# Requisitos: python3, node e playwright com Chromium (npm i -g playwright && npx playwright install chromium).
set -uo pipefail
cd "$(dirname "$0")/.."
export NODE_PATH="$(npm root -g)"
fail=0
echo "== 1/22 verificações estáticas";      python3 tests/static_checks.py | tail -3          || fail=1
echo "== 2/22 ciclo automático da fila";    python3 tests/loop_test.py 2>&1 | grep -v '^\['   || fail=1
echo "== 3/22 avisos, retomada e funil"; python3 tests/automation_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 4/22 custos, A/B, CRM/agenda e backup"; python3 tests/ops_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 5/22 resumo diário e conectores Pipedrive/HubSpot"; python3 tests/connectors_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 6/22 vários números (linhas)"; python3 tests/lines_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 7/22 kit do operador (hospedagem por cliente)"; python3 tests/deploy_test.py 2>&1 | tail -2 || fail=1
echo "== 8/22 regras (QR, consentimento, supressão, LGPD)"; python3 tests/rules_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 9/22 cobrança do operador e avisos"; python3 tests/billing_test.py 2>&1 | tail -2 || fail=1
echo "== 10/22 catálogo e base de conhecimento"; python3 tests/sales_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 11/22 pagamento e fechamento"; python3 tests/pay_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 12/22 simulador de avaliação"; python3 tests/eval_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 13/22 leitura de arquivos (JPG, PDF, áudio e vídeo)"; python3 tests/media_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 14/22 fotos de perfil no chat"; python3 tests/avatar_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 15/22 transferência para atendente humano"; python3 tests/handoff_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 16/22 materiais, janela de 24 h e novos tipos recebidos"; python3 tests/materials_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 17/22 recursos da equipe (horário, respostas rápidas, notas, métricas)"; python3 tests/team_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 18/22 Google Agenda (horários livres e evento)"; python3 tests/gcal_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 19/22 cópia externa do backup (Supabase)"; python3 tests/offsite_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 20/22 piloto"; python3 tests/pilot_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 21/22 conector do WhatsApp";        node tests/gateway_test.js | tail -4               || fail=1
echo "== 22/22 painel no navegador (E2E)";   node tests/e2e.js | tail -4                       || fail=1
[ $fail -eq 0 ] && echo "TUDO CERTO" || echo "HOUVE FALHAS"
exit $fail
