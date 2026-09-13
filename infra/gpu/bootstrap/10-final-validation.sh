#!/usr/bin/env bash
# 10-final-validation.sh — agrega tudo que os scripts 00-09 gravaram em
# $GPU_ENGINE_RESULTS_FILE e decide se o bootstrap, como um todo, está pronto.
#
#   ./10-final-validation.sh [--dry-run] [--report]
#
# --report também gera GPU_ENGINE_REPORT_<timestamp>.json/.md em infra/gpu/reports/
# via services/gpu_engine (dhf_gpu_engine.reports) — precisa do workspace uv sincronizado.

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="10-final-validation"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
WANT_REPORT=0
for arg in "${REMAINING_ARGS[@]:-}"; do
    [ "$arg" = "--report" ] && WANT_REPORT=1
done

log_info "=== Validação final — agregando $GPU_ENGINE_RESULTS_FILE ==="

if [ ! -f "$GPU_ENGINE_RESULTS_FILE" ]; then
    log_error "Nenhum resultado encontrado em $GPU_ENGINE_RESULTS_FILE — rode 00-preflight.sh em diante antes deste script."
    exit 1
fi

python3 - "$GPU_ENGINE_RESULTS_FILE" <<'PYEOF'
import json
import sys
from collections import Counter

path = sys.argv[1]
counts = Counter()
fails = []
requires_gpu = []

with open(path) as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        counts[row["status"]] += 1
        if row["status"] == "FAIL":
            fails.append(row)
        elif row["status"] == "REQUIRES_GPU":
            requires_gpu.append(row)

total = sum(counts.values())
print(f"\nTotal de checagens: {total}")
for status in ("PASS", "WARN", "FAIL", "SKIP", "NOT_TESTED", "REQUIRES_GPU"):
    if counts.get(status):
        print(f"  {status:14s} {counts[status]}")

if fails:
    print("\nFAIL:")
    for row in fails:
        print(f"  - [{row['script']}] {row['name']}: {row['detail']}")

if requires_gpu:
    print("\nREQUIRES_GPU (esperado sem hardware real; obrigatório checar no nó Hostinger):")
    for row in requires_gpu:
        print(f"  - [{row['script']}] {row['name']}: {row['detail']}")

sys.exit(1 if fails else 0)
PYEOF
AGGREGATE_EXIT=$?

if [ "$AGGREGATE_EXIT" -ne 0 ]; then
    record_result "bootstrap_geral" FAIL "há FAIL(s) real(is) registrados — ver acima"
else
    record_result "bootstrap_geral" PASS "nenhum FAIL registrado (REQUIRES_GPU/NOT_TESTED não contam como falha — são honestos sobre o que não pôde ser testado aqui)"
fi

if [ "$WANT_REPORT" = "1" ]; then
    log_info "Gerando relatório via services/gpu_engine..."
    if command_exists uv; then
        (cd "$REPO_ROOT" && uv run --project services/gpu_engine dhf-gpu report --results "$GPU_ENGINE_RESULTS_FILE" --out infra/gpu/reports) \
            || log_warn "geração de relatório falhou — checar se 'uv sync --all-packages' já rodou no monorepo"
    else
        log_warn "'uv' não encontrado — pulando geração de relatório (rode 08-python-ai.sh primeiro)"
    fi
fi

exit "$AGGREGATE_EXIT"
