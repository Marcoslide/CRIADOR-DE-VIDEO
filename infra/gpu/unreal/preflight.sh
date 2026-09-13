#!/usr/bin/env bash
# preflight.sh — roda verify-requirements.sh e emite o veredito único pedido na seção 25
# da missão: UNREAL_READY_FOR_INSTALL: YES/NO. Nunca aceita licença automaticamente —
# isso é e continua sendo uma ação humana (Epic End User License Agreement).
#
#   ./preflight.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="unreal-preflight"

"$HERE/verify-requirements.sh"

# Conta quantos FAIL reais (não WARN) apareceram nas linhas gravadas por este script
# nesta mesma execução do preflight — WARN não bloqueia (ex.: clang ausente é
# corrigível com um apt install; glibc antiga não é).
#
# NUNCA usar `grep -c ... || echo 0` aqui: grep -c IMPRIME "0" e retorna exit 1 quando
# não encontra nada — o fallback rodaria por cima dessa saída já impressa, duplicando o
# valor (o mesmo bug de concatenação encontrado e corrigido em network-benchmark.sh).
FAIL_COUNT="$(grep -c '"script":"unreal-verify-requirements".*"status":"FAIL"' "$GPU_ENGINE_RESULTS_FILE" 2>/dev/null)"
FAIL_COUNT="${FAIL_COUNT:-0}"

echo
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "UNREAL_READY_FOR_INSTALL: YES"
    record_result "unreal_ready_for_install" PASS "nenhum FAIL crítico — WARNs (se houver) são corrigíveis antes do build"
    exit 0
else
    echo "UNREAL_READY_FOR_INSTALL: NO"
    record_result "unreal_ready_for_install" FAIL "$FAIL_COUNT requisito(s) crítico(s) não atendido(s) — ver verify-requirements.sh acima"
    exit 1
fi
