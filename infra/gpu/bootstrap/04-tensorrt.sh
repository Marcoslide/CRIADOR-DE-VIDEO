#!/usr/bin/env bash
# 04-tensorrt.sh — TensorRT via pip wheel oficial (ver versions.env).
#
#   ./04-tensorrt.sh [--dry-run]

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="04-tensorrt"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

PIP_PACKAGE="${TENSORRT_PIP_PACKAGE:-tensorrt-cu13}"

log_info "=== FASE B / TensorRT ($PIP_PACKAGE) ==="

if ! command_exists python3; then
    record_result "python3" FAIL "python3 não encontrado — rode 08-python-ai.sh antes deste script" 1
    exit 1
fi

CURRENT_VERSION="$(python3 -c 'import tensorrt; print(tensorrt.__version__)' 2>/dev/null || true)"
if [ -n "$CURRENT_VERSION" ]; then
    record_result "tensorrt_pacote" PASS "SKIP — tensorrt $CURRENT_VERSION já importável"
else
    run_cmd "pip install $PIP_PACKAGE" -- python3 -m pip install --upgrade "$PIP_PACKAGE"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "tensorrt_pacote" NOT_TESTED "dry-run"
    else
        NEW_VERSION="$(python3 -c 'import tensorrt; print(tensorrt.__version__)' 2>/dev/null || true)"
        if [ -n "$NEW_VERSION" ]; then
            record_result "tensorrt_pacote" PASS "instalado: $NEW_VERSION"
        else
            record_result "tensorrt_pacote" FAIL "pip install rodou mas 'import tensorrt' ainda falha — checar log acima"
        fi
    fi
fi

log_info "04-tensorrt.sh concluído. Validação funcional real: infra/gpu/diagnostics/tensorrt-test.py (precisa de GPU)."
