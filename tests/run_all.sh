#!/usr/bin/env bash
# Roda todos os testes que não precisam de internet nem de chaves (usa simulações de WhatsApp, Claude e Whisper).
# Requisitos: python3, node e playwright com Chromium (npm i -g playwright && npx playwright install chromium).
set -uo pipefail
cd "$(dirname "$0")/.."
export NODE_PATH="$(npm root -g)"
fail=0
echo "== 1/40 verificações estáticas";      python3 tests/static_checks.py | tail -3          || fail=1
echo "== 2/40 ciclo automático da fila";    python3 tests/loop_test.py 2>&1 | grep -v '^\['   || fail=1
echo "== 3/40 avisos, retomada e funil"; python3 tests/automation_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 4/40 custos, A/B, CRM/agenda e backup"; python3 tests/ops_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 5/40 resumo diário e conectores Pipedrive/HubSpot"; python3 tests/connectors_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 6/40 vários números (linhas)"; python3 tests/lines_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 7/40 kit do operador (hospedagem por cliente)"; python3 tests/deploy_test.py 2>&1 | tail -2 || fail=1
echo "== 8/40 regras (QR, consentimento, supressão, LGPD)"; python3 tests/rules_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 9/40 cobrança do operador e avisos"; python3 tests/billing_test.py 2>&1 | tail -2 || fail=1
echo "== 10/40 catálogo e base de conhecimento"; python3 tests/sales_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 11/40 pagamento e fechamento"; python3 tests/pay_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 12/40 simulador de avaliação"; python3 tests/eval_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 13/40 leitura de arquivos (JPG, PDF, áudio e vídeo)"; python3 tests/media_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 14/40 fotos de perfil no chat"; python3 tests/avatar_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 15/40 transferência para atendente humano"; python3 tests/handoff_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 16/40 materiais, janela de 24 h e novos tipos recebidos"; python3 tests/materials_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 17/40 recursos da equipe (horário, respostas rápidas, notas, métricas)"; python3 tests/team_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 18/40 Google Agenda (horários livres e evento)"; python3 tests/gcal_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 19/40 cópia externa do backup (Supabase)"; python3 tests/offsite_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 20/40 piloto"; python3 tests/pilot_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 21/40 gestor de equipe (número próprio, equipe própria, isolamento)"; python3 tests/manager_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 22/40 app no celular (avisos push, PWA)"; python3 tests/push_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 23/40 histórico de ações (auditoria)"; python3 tests/audit_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 24/40 etiquetas, quadro e filtros"; python3 tests/tags_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 25/40 roteiros e resposta fora do horário"; python3 tests/flows_test.py 2>&1 | grep -v '^\[' | grep -v '^[0-9]) \|^$' | tail -3 || fail=1
echo "== 26/40 verificação em duas etapas e supervisor"; python3 tests/twofa_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 27/40 disparo e agenda do gestor"; python3 tests/gestor_extra_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 28/40 plano de aquecimento de 14 dias"; python3 tests/warmup_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 29/40 aprender com conversas reais (insights e casos de teste)"; python3 tests/insights_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 30/40 emojis do agente"; python3 tests/emoji_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 31/40 PDF na base de conhecimento"; python3 tests/kbpdf_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 32/40 prospecção por Google (busca, fila, supressão, rede interna)"; python3 tests/prospect_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 33/40 revisão antes de enviar (valores, descontos e prazos)"; python3 tests/review_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 34/40 memória por lead (resumo das conversas longas)"; python3 tests/memory_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 35/40 playbook de objeções"; python3 tests/playbook_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 36/40 prontidão da API oficial (checklist, templates, teste)"; python3 tests/official_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 37/40 variações da abertura (rodízio, SAIR e medição)"; python3 tests/openings_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 38f/45 prévia do disparo e resumo diário"; python3 tests/dispatchprev_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 38e/44 contatos pessoais protegidos"; python3 tests/personal_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 38d/43 agente fixo por número"; python3 tests/linenicho_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 38c/42 nicho pronto Energia solar"; python3 tests/energia_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 38b/41 assistente de primeira configuração"; python3 tests/setup_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 38/40 nome do agente que dispara ({agente})"; python3 tests/persona_test.py 2>&1 | grep -v '^\[' | tail -3 || fail=1
echo "== 39/40 conector do WhatsApp";        node tests/gateway_test.js | tail -4               || fail=1
echo "== 40/40 painel no navegador (E2E)";   node tests/e2e.js | tail -4                       || fail=1
[ $fail -eq 0 ] && echo "TUDO CERTO" || echo "HOUVE FALHAS"
exit $fail
