#!/usr/bin/env bash
# Roda todos os testes que não precisam de internet nem de chaves (usa simulações de WhatsApp, Claude e Whisper).
# Requisitos: python3, node e playwright com Chromium (npm i -g playwright && npx playwright install chromium).
set -uo pipefail
cd "$(dirname "$0")/.."
export NODE_PATH="$(npm root -g)"
fail=0
echo "== 1/27 verificações estáticas";      python3 tests/static_checks.py | tail -3          || fail=1
echo "== 2/27 ciclo automático da fila";    python3 tests/loop_test.py 2>&1 | grep -v '^\['   || fail=1
echo "== 3/27 avisos, retomada e funil"; python3 tests/automation_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 4/27 custos, A/B, CRM/agenda e backup"; python3 tests/ops_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 5/27 resumo diário e conectores Pipedrive/HubSpot"; python3 tests/connectors_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 6/27 vários números (linhas)"; python3 tests/lines_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 7/27 kit do operador (hospedagem por cliente)"; python3 tests/deploy_test.py 2>&1 | tail -2 || fail=1
echo "== 8/27 regras (QR, consentimento, supressão, LGPD)"; python3 tests/rules_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 9/27 cobrança do operador e avisos"; python3 tests/billing_test.py 2>&1 | tail -2 || fail=1
echo "== 10/27 catálogo e base de conhecimento"; python3 tests/sales_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 11/27 pagamento e fechamento"; python3 tests/pay_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 12/27 simulador de avaliação"; python3 tests/eval_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 13/27 leitura de arquivos (JPG, PDF, áudio e vídeo)"; python3 tests/media_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 14/27 fotos de perfil no chat"; python3 tests/avatar_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 15/27 transferência para atendente humano"; python3 tests/handoff_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 16/27 materiais, janela de 24 h e novos tipos recebidos"; python3 tests/materials_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 17/27 recursos da equipe (horário, respostas rápidas, notas, métricas)"; python3 tests/team_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 18/27 Google Agenda (horários livres e evento)"; python3 tests/gcal_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 19/27 cópia externa do backup (Supabase)"; python3 tests/offsite_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 20/27 piloto"; python3 tests/pilot_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 21/27 gestor de equipe (número próprio, equipe própria, isolamento)"; python3 tests/manager_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 22/27 app no celular (avisos push, PWA)"; python3 tests/push_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 23/27 histórico de ações (auditoria)"; python3 tests/audit_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 24/27 etiquetas, quadro e filtros"; python3 tests/tags_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 25/27 roteiros e resposta fora do horário"; python3 tests/flows_test.py 2>&1 | grep -v '^\[' | grep -v '^[0-9]) \|^$' | tail -3 || fail=1
echo "== 26/27 conector do WhatsApp";        node tests/gateway_test.js | tail -4               || fail=1
echo "== 27/27 painel no navegador (E2E)";   node tests/e2e.js | tail -4                       || fail=1
[ $fail -eq 0 ] && echo "TUDO CERTO" || echo "HOUVE FALHAS"
exit $fail
