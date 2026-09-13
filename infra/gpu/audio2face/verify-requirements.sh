#!/usr/bin/env bash
# verify-requirements.sh — requisitos do NVIDIA Audio2Face-3D NIM (microserviço Docker;
# o app standalone Omniverse legado teve o launcher descontinuado em 10/2025 — ver
# infra/gpu/README.md). Seção 27 da missão.
#
# Fonte: docs.nvidia.com/ace/audio2face-3d-microservice/latest/text/support-matrix.html
# (via busca indexada — fetch direto bloqueado pela rede deste ambiente).
#
#   ./verify-requirements.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="audio2face-verify-requirements"
load_versions

log_info "=== NVIDIA Audio2Face-3D (NIM) — requisitos ==="

if command_exists docker; then
    record_result "docker" PASS "$(docker --version 2>/dev/null)"
else
    record_result "docker" FAIL "docker não instalado — Audio2Face-3D hoje só é distribuído como container NIM"
fi

if command_exists nvidia-ctk; then
    record_result "nvidia_container_toolkit" PASS "presente"
else
    record_result "nvidia_container_toolkit" FAIL "ausente — necessário para o container NIM acessar a GPU"
fi

if has_nvidia_gpu; then
    VRAM_TOTAL="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d '[:space:]')"
    # ~2-4.5GB por stream documentado — 24GB da RTX 4090 comporta múltiplos streams
    # concorrentes com folga para o resto do pipeline (Unreal/MetaHuman/TTS).
    if [ -n "$VRAM_TOTAL" ] && [ "$VRAM_TOTAL" -ge 8192 ]; then
        record_result "vram_suficiente" PASS "${VRAM_TOTAL}MB — comporta múltiplos streams de Audio2Face-3D (~2-4.5GB cada) + resto do pipeline"
    else
        record_result "vram_suficiente" WARN "${VRAM_TOTAL:-desconhecida}MB — pode não sobrar VRAM suficiente com outros engines carregados ao mesmo tempo"
    fi
else
    record_result "vram_suficiente" REQUIRES_GPU "sem GPU neste ambiente"
fi

# NGC_API_KEY: nunca commitada (mesmo princípio de GOOGLE_DRIVE_ACTIVATION.md) — só
# checamos SE existe na env, nunca imprimimos o valor.
if [ -n "${NGC_API_KEY:-}" ]; then
    record_result "ngc_api_key" PASS "configurada (valor não exibido)"
else
    record_result "ngc_api_key" WARN "NGC_API_KEY não configurada — necessária para baixar o container NIM de nvcr.io ou usar a API hospedada em build.nvidia.com. Ação manual do Marcos: criar conta NGC + gerar API key."
fi

if command_exists python3; then
    record_result "python3" PASS "$(python3 --version 2>/dev/null)"
else
    record_result "python3" WARN "python3 não encontrado — SDK/cliente de exemplo do Audio2Face-3D é Python"
fi

log_info "audio2face/verify-requirements.sh concluído."
