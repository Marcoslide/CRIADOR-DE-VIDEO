#!/usr/bin/env bash
# 06-nvidia-container-toolkit.sh — permite `docker run --gpus all` (repositório oficial).
#
#   ./06-nvidia-container-toolkit.sh [--dry-run]

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="06-nvidia-container-toolkit"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

log_info "=== FASE B / NVIDIA Container Toolkit ==="

if ! command_exists docker; then
    record_result "docker_presente" FAIL "docker não instalado — rode 05-docker.sh primeiro" 1
    exit 1
fi

if command_exists nvidia-ctk; then
    record_result "nvidia_container_toolkit_pacote" PASS "SKIP — $(nvidia-ctk --version 2>/dev/null | head -1)"
else
    run_cmd "adicionar repositório NVIDIA Container Toolkit" -- bash -c "
        set -e
        curl -fsSL '$NVIDIA_CONTAINER_TOOLKIT_KEYRING_URL' \
            | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -fsSL '$NVIDIA_CONTAINER_TOOLKIT_LIST_URL' \
            | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
            > /etc/apt/sources.list.d/nvidia-container-toolkit.list
        apt-get update -qq
    "
    run_cmd "instalar nvidia-container-toolkit" -- apt-get install -y -qq nvidia-container-toolkit
    if [ "$DRY_RUN" = "1" ]; then
        record_result "nvidia_container_toolkit_pacote" NOT_TESTED "dry-run"
    else
        record_result "nvidia_container_toolkit_pacote" PASS "$(nvidia-ctk --version 2>/dev/null | head -1)"
    fi
fi

run_cmd "nvidia-ctk runtime configure --runtime=docker" -- nvidia-ctk runtime configure --runtime=docker
run_cmd "reiniciar docker" -- systemctl restart docker
if [ "$DRY_RUN" != "1" ]; then
    if docker info 2>/dev/null | grep -qi nvidia; then
        record_result "docker_runtime_nvidia" PASS "runtime nvidia registrado no Docker"
    else
        record_result "docker_runtime_nvidia" WARN "runtime nvidia não apareceu em 'docker info' — checar /etc/docker/daemon.json"
    fi
fi

# --- teste funcional real: container + nvidia-smi -------------------------------------
if [ "$DRY_RUN" = "1" ]; then
    record_result "docker_gpu_test" NOT_TESTED "dry-run"
elif has_nvidia_gpu; then
    CUDA_TAG="${CUDA_TOOLKIT_VERSION:-12.9}.0-base-ubuntu24.04"
    if docker run --rm --gpus all "nvidia/cuda:$CUDA_TAG" nvidia-smi >/dev/null 2>&1; then
        record_result "docker_gpu_test" PASS "container 'nvidia/cuda:$CUDA_TAG' viu a GPU corretamente"
    else
        record_result "docker_gpu_test" FAIL "docker run --gpus all falhou — ver seção 15 da missão (DOCKER_GPU = FAIL é um resultado válido a reportar, não a esconder)"
    fi
else
    record_result "docker_gpu_test" REQUIRES_GPU "sem GPU neste ambiente — teste real só é possível no nó Hostinger"
fi

log_info "06-nvidia-container-toolkit.sh concluído."
