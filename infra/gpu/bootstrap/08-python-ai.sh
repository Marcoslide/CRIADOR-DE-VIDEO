#!/usr/bin/env bash
# 08-python-ai.sh — uv (mesmo gerenciador do monorepo) + PyTorch com suporte a CUDA.
#
#   ./08-python-ai.sh [--dry-run]

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="08-python-ai"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

log_info "=== FASE D / Python + PyTorch ==="

if command_exists uv; then
    record_result "uv" PASS "SKIP — $(uv --version 2>/dev/null)"
else
    run_cmd "instalar uv" -- bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "uv" NOT_TESTED "dry-run"
    else
        record_result "uv" PASS "instalado — pode exigir novo shell para entrar no PATH"
    fi
fi

CUDA_TAG="${PYTORCH_CUDA_INDEX_TAG:-cu128}"
CURRENT_TORCH="$(python3 -c 'import torch; print(torch.__version__)' 2>/dev/null || true)"
if [ -n "$CURRENT_TORCH" ]; then
    record_result "pytorch_pacote" PASS "SKIP — torch $CURRENT_TORCH já instalado"
else
    run_cmd "pip install torch (index $CUDA_TAG)" -- python3 -m pip install torch torchvision torchaudio \
        --index-url "https://download.pytorch.org/whl/$CUDA_TAG"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "pytorch_pacote" NOT_TESTED "dry-run"
    else
        NEW_TORCH="$(python3 -c 'import torch; print(torch.__version__)' 2>/dev/null || true)"
        if [ -n "$NEW_TORCH" ]; then
            record_result "pytorch_pacote" PASS "instalado: $NEW_TORCH"
        else
            record_result "pytorch_pacote" FAIL "pip install rodou mas 'import torch' ainda falha"
        fi
    fi
fi

log_info "08-python-ai.sh concluído. Validação funcional real: infra/gpu/diagnostics/pytorch-test.py (precisa de GPU)."
