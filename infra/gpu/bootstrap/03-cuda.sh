#!/usr/bin/env bash
# 03-cuda.sh — CUDA Toolkit (ver infra/gpu/config/versions.env para a versão-alvo).
#
#   ./03-cuda.sh [--dry-run]

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="03-cuda"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

PACKAGE="${CUDA_TOOLKIT_APT_PACKAGE:-cuda-toolkit-13-4}"

log_info "=== FASE B / CUDA Toolkit ($PACKAGE) ==="

INSTALLED_VERSION="$(installed_apt_version "$PACKAGE")"
if [ -n "$INSTALLED_VERSION" ]; then
    record_result "cuda_toolkit_pacote" PASS "SKIP — $PACKAGE $INSTALLED_VERSION já instalado"
else
    run_cmd "instalar $PACKAGE (assume keyring já configurado por 02-nvidia-driver.sh)" \
        -- apt-get install -y -qq "$PACKAGE"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "cuda_toolkit_pacote" NOT_TESTED "dry-run"
    else
        record_result "cuda_toolkit_pacote" PASS "$PACKAGE instalado"
    fi
fi

# Garante que /usr/local/cuda/bin está no PATH para o usuário de operação, sem duplicar
# a linha se rodar de novo (idempotência do próprio arquivo de perfil).
PROFILE_LINE='export PATH=/usr/local/cuda/bin:$PATH'
PROFILE_FILE="/etc/profile.d/cuda.sh"
if [ -f "$PROFILE_FILE" ] && grep -qF "$PROFILE_LINE" "$PROFILE_FILE" 2>/dev/null; then
    record_result "cuda_path" PASS "SKIP — $PROFILE_FILE já configurado"
else
    run_cmd "escrever $PROFILE_FILE" -- bash -c "echo '$PROFILE_LINE' > '$PROFILE_FILE'"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "cuda_path" NOT_TESTED "dry-run — simularia criar $PROFILE_FILE"
    else
        record_result "cuda_path" PASS "$PROFILE_FILE criado (efetivo na próxima sessão de shell)"
    fi
fi

if command_exists nvcc || [ -x /usr/local/cuda/bin/nvcc ]; then
    NVCC_BIN="$(command -v nvcc || echo /usr/local/cuda/bin/nvcc)"
    record_result "nvcc" PASS "$("$NVCC_BIN" --version 2>/dev/null | tail -1)"
else
    if [ "$DRY_RUN" = "1" ]; then
        record_result "nvcc" NOT_TESTED "dry-run"
    else
        record_result "nvcc" WARN "nvcc não encontrado no PATH — abrir um novo shell (ou 'source $PROFILE_FILE') antes de validar"
    fi
fi

log_info "03-cuda.sh concluído. Validação funcional real: infra/gpu/diagnostics/cuda-test.py (precisa de GPU)."
