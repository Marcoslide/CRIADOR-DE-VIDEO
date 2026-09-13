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

PIP_PACKAGE="${TENSORRT_PIP_PACKAGE:-tensorrt-cu12}"
MIN_VERSION="${TENSORRT_MIN_VERSION:-10.13.0}"
MAX_VERSION_EXCLUSIVE="${TENSORRT_MAX_VERSION_EXCLUSIVE:-11.0.0}"
# Faixa fixada no `pip install` — sem isso, "pip install tensorrt-cu12" sem versão
# instalaria sempre o mais novo publicado sob essa tag, que pode um dia ultrapassar o
# teto de compatibilidade do Audio2Face-3D SDK (>=10.13,<11.0 — ver config/versions.env).
PIP_SPEC="${PIP_PACKAGE}>=${MIN_VERSION},<${MAX_VERSION_EXCLUSIVE}"

log_info "=== FASE B / TensorRT ($PIP_SPEC) ==="

if ! command_exists python3; then
    record_result "python3" FAIL "python3 não encontrado — rode 08-python-ai.sh antes deste script" 1
    exit 1
fi

CURRENT_VERSION="$(python3 -c 'import tensorrt; print(tensorrt.__version__)' 2>/dev/null || true)"
if [ -n "$CURRENT_VERSION" ]; then
    if version_in_range "$CURRENT_VERSION" "$MIN_VERSION" "$MAX_VERSION_EXCLUSIVE"; then
        record_result "tensorrt_pacote" PASS "SKIP — tensorrt $CURRENT_VERSION já importável (dentro da faixa >=$MIN_VERSION,<$MAX_VERSION_EXCLUSIVE)"
    else
        record_result "tensorrt_pacote" FAIL "tensorrt $CURRENT_VERSION instalado está FORA da faixa compatível >=$MIN_VERSION,<$MAX_VERSION_EXCLUSIVE (teto do Audio2Face-3D SDK) — desinstalar e rodar 'pip install \"$PIP_SPEC\"' manualmente"
    fi
else
    run_cmd "pip install $PIP_SPEC" -- python3 -m pip install --upgrade "$PIP_SPEC"
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
