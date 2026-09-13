#!/usr/bin/env bash
# verify-requirements.sh — checagem detalhada, item a item, dos requisitos de
# compilação/execução do Unreal Engine 5.8 no Linux (seção 25 da missão). Não decide
# "pronto ou não" — isso é preflight.sh, que chama este script e agrega o resultado.
#
# Fonte: dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-requirements-for-unreal-engine
# (pesquisa via busca indexada nesta sessão — WebFetch direto bloqueado pela política de
# rede deste ambiente; reconfirmar manualmente antes de depender disso em produção).
#
#   ./verify-requirements.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="unreal-verify-requirements"

log_info "=== Unreal Engine 5.8 — requisitos Linux (detalhado) ==="

# --- glibc (Epic exige >=2.35 para UE5 recente) --------------------------------------
GLIBC_VERSION="$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)"
if [ -n "$GLIBC_VERSION" ] && awk -v v="$GLIBC_VERSION" 'BEGIN { exit !(v >= 2.35) }'; then
    record_result "glibc" PASS "$GLIBC_VERSION (>= 2.35 exigido)"
else
    record_result "glibc" FAIL "$GLIBC_VERSION — abaixo de 2.35"
fi

# --- toolchain de build (clang é o compilador recomendado pela Epic para Linux) -------
if command_exists clang; then
    record_result "clang" PASS "$(clang --version 2>/dev/null | head -1)"
else
    record_result "clang" WARN "clang não instalado — 'apt install clang' (Epic recomenda clang, não só gcc, para builds Linux)"
fi

for pkg in build-essential libssl-dev libx11-dev; do
    if dpkg -l 2>/dev/null | grep -qE "^ii\s+$pkg\s"; then
        record_result "pacote_$pkg" PASS "instalado"
    else
        record_result "pacote_$pkg" WARN "'$pkg' não instalado — 'apt install $pkg'"
    fi
done

# --- Vulkan (RHI principal do Unreal no Linux) ---------------------------------------
if command_exists vulkaninfo; then
    if vulkaninfo --summary >/dev/null 2>&1; then
        DEVICE="$(vulkaninfo --summary 2>/dev/null | grep -m1 'deviceName' | cut -d= -f2 | sed 's/^ *//')"
        record_result "vulkan_runtime" PASS "dispositivo: ${DEVICE:-detectado}"
    else
        record_result "vulkan_runtime" REQUIRES_GPU "vulkaninfo instalado mas nenhum dispositivo Vulkan respondeu — normal sem GPU"
    fi
else
    record_result "vulkan_runtime" WARN "vulkaninfo não instalado — 'apt install vulkan-tools mesa-vulkan-drivers' (ou o driver NVIDIA já traz o ICD Vulkan)"
fi

# --- acesso ao código-fonte (não é um pacote — é uma autorização de conta) -----------
record_result "acesso_repo_epic" WARN "NÃO AUTOMATIZÁVEL — requer vincular a conta GitHub à conta Epic Games (dev.epicgames.com/documentation/unreal-engine/downloading-source-code-in-unreal-engine) antes de clonar github.com/EpicGames/UnrealEngine. Ação manual do Marcos."

# --- display / headless ---------------------------------------------------------------
if [ -n "${DISPLAY:-}" ]; then
    record_result "display" PASS "DISPLAY=$DISPLAY (sessão com display)"
else
    record_result "display" WARN "sem \$DISPLAY — normal num servidor headless; Movie Render Queue em linha de comando não precisa de display real, mas o Editor completo sim (considerar Xvfb se precisar do Editor gráfico remotamente)"
fi

# --- disco (build do Unreal do zero consome dezenas de GB) ---------------------------
DISK_AVAIL_GB="$(df -BG --output=avail "$HERE" 2>/dev/null | tail -1 | tr -dc '0-9')"
DISK_AVAIL_GB="${DISK_AVAIL_GB:-0}"
if [ "$DISK_AVAIL_GB" -ge 100 ]; then
    record_result "disco_build_unreal" PASS "${DISK_AVAIL_GB}GB livres"
else
    record_result "disco_build_unreal" WARN "${DISK_AVAIL_GB}GB livres — um clone+build completo do Unreal Engine facilmente passa de 100GB"
fi

log_info "unreal/verify-requirements.sh concluído."
