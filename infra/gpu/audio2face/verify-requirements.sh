#!/usr/bin/env bash
# verify-requirements.sh — requisitos do NVIDIA Audio2Face-3D (seção 27 da missão).
#
# CORRIGIDO (revisão pós-PR#4): a primeira versão deste arquivo tratava Audio2Face-3D
# como se só existisse distribuído via NIM. Isso estava errado — a NVIDIA oferece dois
# caminhos de distribuição independentes, com requisitos DIFERENTES:
#
#   local_sdk (padrão, AUDIO2FACE_MODE=local_sdk) — Audio2Face-3D SDK (C++/Python,
#       MIT license, github.com/NVIDIA/Audio2Face-3D-SDK) + modelo oficial (NVIDIA Open
#       Model License, Hugging Face) rodando localmente via CUDA/TensorRT na própria
#       GPU. NÃO precisa de Docker, NVIDIA Container Toolkit nem NGC_API_KEY.
#   nim (opcional, AUDIO2FACE_MODE=nim) — Audio2Face NIM: container de deployment
#       escalável/multi-tenant via NGC. Produto separado do SDK, não um pré-requisito
#       dele. Só faz sentido se/quando houver necessidade real de deployment escalável
#       fora do escopo deste V1.
#
# Fonte da faixa de compatibilidade do local_sdk: github.com/NVIDIA/Audio2Face-3D-SDK
# (README, fetch direto confirmado em set/2026) — CUDA >=12.8,<13.0 (12.9 recomendado),
# TensorRT >=10.13,<11.0. Ver infra/gpu/config/versions.env (AUDIO2FACE_* vars).
#
#   ./verify-requirements.sh                       # usa AUDIO2FACE_MODE de versions.env
#   AUDIO2FACE_MODE=nim ./verify-requirements.sh    # força o modo NIM

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="audio2face-verify-requirements"
load_versions

MODE="${AUDIO2FACE_MODE:-local_sdk}"

case "$MODE" in
    local_sdk | nim) ;;
    *)
        record_result "audio2face_mode" FAIL "AUDIO2FACE_MODE='$MODE' inválido — use 'local_sdk' (padrão) ou 'nim'"
        exit 1
        ;;
esac

log_info "=== NVIDIA Audio2Face-3D — requisitos (modo: $MODE) ==="
record_result "audio2face_mode" PASS "modo selecionado: $MODE"

# --- GPU / VRAM (comum aos dois modos) ------------------------------------------------
if has_nvidia_gpu; then
    VRAM_TOTAL="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d '[:space:]')"
    # README oficial do SDK recomenda 4GB+ de VRAM; NIM documenta ~2-4.5GB/stream — a
    # RTX 4090 (24GB) comporta qualquer um dos dois modos com folga para o resto do
    # pipeline (Unreal/MetaHuman/TTS).
    if [ -n "$VRAM_TOTAL" ] && [ "$VRAM_TOTAL" -ge 8192 ]; then
        record_result "audio2face_vram" PASS "${VRAM_TOTAL}MB — suficiente para Audio2Face-3D ($MODE) + resto do pipeline"
    else
        record_result "audio2face_vram" WARN "${VRAM_TOTAL:-desconhecida}MB — pode não sobrar VRAM suficiente com outros engines carregados ao mesmo tempo"
    fi
else
    record_result "audio2face_vram" REQUIRES_GPU "sem GPU neste ambiente"
fi

if [ "$MODE" = "local_sdk" ]; then
    # ---- LOCAL_SDK: CUDA/TensorRT locais dentro da faixa do SDK, build tools, modelo --
    CUDA_MIN="${AUDIO2FACE_CUDA_MIN_VERSION:-12.8}"
    CUDA_MAX_EXCL="${AUDIO2FACE_CUDA_MAX_VERSION_EXCLUSIVE:-13.0}"
    TRT_MIN="${AUDIO2FACE_TENSORRT_MIN_VERSION:-10.13.0}"
    TRT_MAX_EXCL="${AUDIO2FACE_TENSORRT_MAX_VERSION_EXCLUSIVE:-11.0.0}"

    CUDA_INSTALLED="$(cuda_installed_version || true)"
    if [ -z "$CUDA_INSTALLED" ]; then
        record_result "audio2face_local_sdk_cuda_range" NOT_TESTED "nvcc não encontrado — rode 03-cuda.sh antes deste script (faixa exigida pelo Audio2Face-3D SDK: >=$CUDA_MIN,<$CUDA_MAX_EXCL)"
    elif version_in_range "$CUDA_INSTALLED" "$CUDA_MIN" "$CUDA_MAX_EXCL"; then
        record_result "audio2face_local_sdk_cuda_range" PASS "CUDA $CUDA_INSTALLED dentro da faixa exigida pelo Audio2Face-3D SDK (>=$CUDA_MIN,<$CUDA_MAX_EXCL)"
    else
        record_result "audio2face_local_sdk_cuda_range" FAIL "CUDA $CUDA_INSTALLED FORA da faixa exigida pelo Audio2Face-3D SDK (>=$CUDA_MIN,<$CUDA_MAX_EXCL) — reinstalar via 03-cuda.sh (${CUDA_TOOLKIT_APT_PACKAGE:-cuda-toolkit-12-9})"
    fi

    TRT_INSTALLED="$(tensorrt_installed_version || true)"
    if [ -z "$TRT_INSTALLED" ]; then
        record_result "audio2face_local_sdk_tensorrt_range" NOT_TESTED "pacote python 'tensorrt' não importável — rode 04-tensorrt.sh antes deste script (faixa exigida pelo Audio2Face-3D SDK: >=$TRT_MIN,<$TRT_MAX_EXCL)"
    elif version_in_range "$TRT_INSTALLED" "$TRT_MIN" "$TRT_MAX_EXCL"; then
        record_result "audio2face_local_sdk_tensorrt_range" PASS "TensorRT $TRT_INSTALLED dentro da faixa exigida pelo Audio2Face-3D SDK (>=$TRT_MIN,<$TRT_MAX_EXCL)"
    else
        record_result "audio2face_local_sdk_tensorrt_range" FAIL "TensorRT $TRT_INSTALLED FORA da faixa exigida pelo Audio2Face-3D SDK (>=$TRT_MIN,<$TRT_MAX_EXCL) — reinstalar via 04-tensorrt.sh"
    fi

    # Build tools: o SDK compila C++/CUDA localmente (fetch_deps.sh + CMake) — README
    # oficial pede g++/make (Linux) além de CMake.
    MISSING_BUILD_TOOLS=()
    for tool in gcc g++ make cmake; do
        command_exists "$tool" || MISSING_BUILD_TOOLS+=("$tool")
    done
    if [ "${#MISSING_BUILD_TOOLS[@]}" -eq 0 ]; then
        record_result "audio2face_local_sdk_build_tools" PASS "gcc/g++/make/cmake presentes"
    else
        record_result "audio2face_local_sdk_build_tools" FAIL "faltando: ${MISSING_BUILD_TOOLS[*]} — 'apt-get install -y build-essential cmake'"
    fi

    if command_exists python3; then
        record_result "audio2face_local_sdk_python3" PASS "$(python3 --version 2>/dev/null)"
    else
        record_result "audio2face_local_sdk_python3" WARN "python3 não encontrado — scripts de exemplo/cliente do SDK são Python (o binário C++ compilado não depende disso)"
    fi

    # Modelo oficial (NVIDIA Open Model License, Hugging Face): exige aceite manual da
    # licença + autenticação — não dá para checar por comando, só avisar.
    if command_exists huggingface-cli || python3 -c "import huggingface_hub" >/dev/null 2>&1; then
        record_result "audio2face_local_sdk_model_access" WARN "huggingface_hub/huggingface-cli presente — confirmar manualmente 'huggingface-cli login' e o aceite da NVIDIA Open Model License antes de baixar o modelo"
    else
        record_result "audio2face_local_sdk_model_access" WARN "huggingface_hub/huggingface-cli não encontrado — necessário para autenticar e baixar o modelo oficial Audio2Face-3D (NVIDIA Open Model License, huggingface.co)"
    fi

    # Docker/NGC nunca são requisito do local_sdk — reportado só como informação (nunca
    # FAIL/WARN neste modo), e NGC_API_KEY nem chega a ser avaliada.
    if command_exists docker; then
        record_result "audio2face_docker_info" PASS "docker presente (não exigido pelo modo local_sdk — informativo)"
    else
        record_result "audio2face_docker_info" SKIP "docker ausente — não é requisito do modo local_sdk"
    fi
    record_result "audio2face_ngc_api_key" SKIP "NGC_API_KEY não é necessária no modo local_sdk (só se aplica ao modo nim)"
else
    # ---- NIM: container de deployment escalável via NGC ------------------------------
    if command_exists docker; then
        record_result "audio2face_nim_docker" PASS "$(docker --version 2>/dev/null)"
    else
        record_result "audio2face_nim_docker" FAIL "docker não instalado — obrigatório no modo nim (Audio2Face NIM é um container)"
    fi

    if command_exists nvidia-ctk; then
        record_result "audio2face_nim_nvidia_ctk" PASS "presente"
    else
        record_result "audio2face_nim_nvidia_ctk" FAIL "ausente — necessário no modo nim para o container acessar a GPU"
    fi

    # NGC_API_KEY: nunca commitada (mesmo princípio de GOOGLE_DRIVE_ACTIVATION.md) — só
    # checamos SE existe na env, nunca imprimimos o valor. WARN (não FAIL): depende de
    # uma ação manual do Marcos (criar conta NGC), não de algo que este bootstrap corrija
    # sozinho.
    if [ -n "${NGC_API_KEY:-}" ]; then
        record_result "audio2face_nim_ngc_api_key" PASS "configurada (valor não exibido)"
    else
        record_result "audio2face_nim_ngc_api_key" WARN "NGC_API_KEY não configurada — necessária no modo nim para baixar o container de nvcr.io ou usar a API hospedada em build.nvidia.com. Ação manual do Marcos: criar conta NGC + gerar API key."
    fi

    if command_exists python3; then
        record_result "audio2face_nim_python3" PASS "$(python3 --version 2>/dev/null)"
    else
        record_result "audio2face_nim_python3" WARN "python3 não encontrado — cliente de exemplo do Audio2Face NIM é Python"
    fi
fi

log_info "audio2face/verify-requirements.sh concluído (modo: $MODE)."
