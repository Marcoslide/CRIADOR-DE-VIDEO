#!/usr/bin/env bash
# 02-nvidia-driver.sh — driver NVIDIA proprietário (RTX 4090/Ada Lovelace NÃO exige o
# módulo kernel open-source como a RTX 5090/Blackwell — ver infra/gpu/README.md).
#
#   ./02-nvidia-driver.sh [--dry-run]
#
# Idempotente: se um driver da branch certa (ou mais novo) já está instalado, SKIP.
# Nunca faz downgrade silencioso (seção 11) — se a versão instalada for mais nova que a
# de versions.env, isso é reportado como PASS, não "corrigido".

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="02-nvidia-driver"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

BRANCH="${NVIDIA_DRIVER_BRANCH:-580}"
PACKAGE="${NVIDIA_DRIVER_PACKAGE:-nvidia-driver-$BRANCH}"

log_info "=== FASE B / Driver NVIDIA (branch $BRANCH) ==="

INSTALLED_VERSION="$(installed_apt_version "$PACKAGE")"
if [ -n "$INSTALLED_VERSION" ]; then
    record_result "nvidia_driver_pacote" PASS "SKIP — $PACKAGE $INSTALLED_VERSION já instalado"
elif dpkg -l 2>/dev/null | grep -qE '^ii\s+nvidia-driver-[0-9]+'; then
    OTHER="$(dpkg -l | grep -E '^ii\s+nvidia-driver-[0-9]+' | awk '{print $2}' | head -1)"
    record_result "nvidia_driver_pacote" WARN "outra branch já instalada ($OTHER) — não fazendo downgrade/troca automática; decisão manual se quiser trocar para $PACKAGE"
else
    run_cmd "adicionar keyring CUDA da NVIDIA" -- bash -c "
        set -e
        cd /tmp
        curl -fsSL -o cuda-keyring.deb '$CUDA_KEYRING_URL'
        dpkg -i cuda-keyring.deb
    "
    run_cmd "apt update (repo NVIDIA)" -- apt-get update -qq
    run_cmd "instalar $PACKAGE" -- apt-get install -y -qq "$PACKAGE"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "nvidia_driver_pacote" NOT_TESTED "dry-run — instalação real não executada"
    else
        record_result "nvidia_driver_pacote" PASS "$PACKAGE instalado — REBOOT NECESSÁRIO antes de validar"
    fi
fi

# --- validação pós-instalação (só faz sentido depois do reboot) ----------------------
if has_nvidia_gpu; then
    DRIVER_RUNNING="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"
    record_result "nvidia_smi" PASS "driver ativo: $DRIVER_RUNNING"
else
    if [ "$DRY_RUN" = "1" ]; then
        record_result "nvidia_smi" NOT_TESTED "dry-run"
    else
        record_result "nvidia_smi" REQUIRES_GPU "nvidia-smi não respondeu — normal se ainda não houve reboot pós-instalação, ou se este ambiente não tem GPU (ex.: sandbox de desenvolvimento)"
    fi
fi

log_info "02-nvidia-driver.sh concluído. Se o pacote acabou de ser instalado: sudo reboot, depois rode este script de novo para validar."
