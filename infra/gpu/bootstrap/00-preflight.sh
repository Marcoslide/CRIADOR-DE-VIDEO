#!/usr/bin/env bash
# 00-preflight.sh — checagens antes de instalar QUALQUER COISA (seção 7 da missão).
#
#   ./00-preflight.sh [--dry-run]
#
# Nunca instala nada — só inspeciona o sistema e classifica cada item em PASS/WARN/FAIL.
# Qualquer FAIL crítico aborta com exit 1 (nada nos scripts 01+ deveria rodar depois
# disso sem essas condições corrigidas). --dry-run não muda nada aqui (não há efeito
# colateral neste script de qualquer forma) — aceito só por consistência com os outros.

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="00-preflight"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
: > "$GPU_ENGINE_RESULTS_FILE"  # preflight sempre começa um arquivo de resultados novo

CRITICAL_FAIL=0

check() {
    # check NOME STATUS DETALHE [critico:1|0]
    local name="$1" status="$2" detail="$3" critical="${4:-0}"
    record_result "$name" "$status" "$detail"
    if [ "$status" = "FAIL" ] && [ "$critical" = "1" ]; then
        CRITICAL_FAIL=1
    fi
}

log_info "=== FASE A / Preflight — RTX 4090 studio node ==="

# --- Ubuntu version ------------------------------------------------------------------
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [ "${ID:-}" = "ubuntu" ] && [ "${VERSION_ID:-}" = "24.04" ]; then
        check "ubuntu_version" PASS "Ubuntu ${VERSION_ID} (${VERSION_CODENAME:-?}) — confirmado"
    elif [ "${ID:-}" = "ubuntu" ]; then
        check "ubuntu_version" WARN "Ubuntu ${VERSION_ID:-desconhecida}, esperado 24.04 — scripts foram escritos/testados para 24.04"
    else
        check "ubuntu_version" FAIL "SO detectado: ${ID:-desconhecido} — este bootstrap é só para Ubuntu 24.04" 1
    fi
else
    check "ubuntu_version" FAIL "/etc/os-release não encontrado — não foi possível identificar o SO" 1
fi

# --- kernel ----------------------------------------------------------------------------
KERNEL_VERSION="$(uname -r)"
check "kernel" PASS "$KERNEL_VERSION"

# --- architecture ------------------------------------------------------------------
ARCH="$(uname -m)"
if [ "$ARCH" = "x86_64" ]; then
    check "architecture" PASS "$ARCH"
else
    check "architecture" FAIL "Detectado $ARCH — drivers NVIDIA/CUDA para este projeto só têm build oficial x86_64" 1
fi

# --- CPU -------------------------------------------------------------------------------
CPU_CORES="$(nproc --all 2>/dev/null || echo 0)"
if [ "$CPU_CORES" -ge 16 ]; then
    check "cpu_cores" PASS "$CPU_CORES cores (esperado 32 na instância contratada)"
elif [ "$CPU_CORES" -ge 4 ]; then
    check "cpu_cores" WARN "$CPU_CORES cores — bem abaixo dos 32 esperados; pipeline de vídeo é CPU-bound em partes (FFmpeg/Remotion)"
else
    check "cpu_cores" FAIL "$CPU_CORES cores — insuficiente para qualquer etapa relevante do pipeline"
fi

# --- RAM -------------------------------------------------------------------------------
RAM_MB="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)"
if [ "$RAM_MB" -ge 49152 ]; then
    check "ram" PASS "${RAM_MB}MB (esperado 65536MB / 64GB na instância contratada)"
elif [ "$RAM_MB" -ge 16384 ]; then
    check "ram" WARN "${RAM_MB}MB — abaixo dos 64GB esperados"
else
    check "ram" FAIL "${RAM_MB}MB — insuficiente até para o sistema operacional + Docker rodarem confortavelmente"
fi

# --- disk --------------------------------------------------------------------------
# Nota: o `|| echo 0` seria deadcode aqui — o exit code do pipe é o do último estágio
# (tr), que não falha mesmo com entrada vazia; por isso o default vem de `:-0` depois,
# não do fallback do pipe (mesma classe de cuidado do bug corrigido em
# network-benchmark.sh, mas na direção oposta: aqui o risco é ficar com string vazia).
DISK_AVAIL_GB="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')"
DISK_AVAIL_GB="${DISK_AVAIL_GB:-0}"
if [ "$DISK_AVAIL_GB" -ge 350 ]; then
    check "disk_space" PASS "${DISK_AVAIL_GB}GB livres em / (esperado ~500GB na instância contratada)"
elif [ "$DISK_AVAIL_GB" -ge 50 ]; then
    check "disk_space" WARN "${DISK_AVAIL_GB}GB livres — modelos + cache + renders enchem rápido, monitorar (ver diagnostics/disk-benchmark.sh)"
else
    check "disk_space" FAIL "${DISK_AVAIL_GB}GB livres — insuficiente para instalar CUDA/TensorRT/Unreal (dezenas de GB só de toolchain)"
fi

# --- filesystem --------------------------------------------------------------------
ROOT_FS="$(df --output=fstype / 2>/dev/null | tail -1 | tr -d '[:space:]')"
case "$ROOT_FS" in
    ext4|xfs|btrfs) check "filesystem" PASS "$ROOT_FS" ;;
    *) check "filesystem" WARN "$ROOT_FS — não testado explicitamente com este bootstrap, mas não deve bloquear" ;;
esac

# --- internet / DNS ------------------------------------------------------------------
if command_exists curl && curl -fsS --max-time 5 -o /dev/null "https://developer.download.nvidia.com" 2>/dev/null; then
    check "internet_nvidia" PASS "developer.download.nvidia.com alcançável"
else
    check "internet_nvidia" FAIL "Não foi possível alcançar developer.download.nvidia.com — necessário para baixar driver/CUDA/TensorRT" 1
fi
if command_exists getent && getent hosts github.com >/dev/null 2>&1; then
    check "dns" PASS "resolução de nomes funcionando (github.com resolvido)"
else
    check "dns" WARN "getent indisponível ou falhou ao resolver github.com — checar /etc/resolv.conf"
fi

# --- sudo ------------------------------------------------------------------------------
if [ "$(id -u)" = "0" ]; then
    check "sudo" PASS "rodando como root"
elif command_exists sudo && sudo -n true 2>/dev/null; then
    check "sudo" PASS "sudo sem senha disponível"
elif command_exists sudo; then
    check "sudo" WARN "sudo existe mas exige senha interativa — bootstrap não-interativo (--dry-run ou cron) vai falhar"
else
    check "sudo" FAIL "nem root nem sudo disponível — impossível instalar pacotes de sistema" 1
fi

# --- pacotes/driver/CUDA/Docker já existentes (idempotência começa aqui) -----------
if dpkg -l 2>/dev/null | grep -qE '^ii\s+nvidia-driver-'; then
    EXISTING_DRIVER="$(dpkg -l | grep -E '^ii\s+nvidia-driver-' | awk '{print $2}' | head -1)"
    check "nvidia_driver_existente" PASS "pacote já instalado: $EXISTING_DRIVER (02-nvidia-driver.sh vai pular a instalação)"
else
    check "nvidia_driver_existente" NOT_TESTED "nenhum pacote nvidia-driver-* instalado ainda — normal antes do bootstrap"
fi

if command_exists nvcc; then
    check "cuda_existente" PASS "$(nvcc --version 2>/dev/null | tail -1)"
else
    check "cuda_existente" NOT_TESTED "nvcc não encontrado — normal antes do bootstrap"
fi

if command_exists docker; then
    check "docker_existente" PASS "$(docker --version 2>/dev/null)"
else
    check "docker_existente" NOT_TESTED "docker não encontrado — normal antes do bootstrap"
fi

# --- Vulkan ------------------------------------------------------------------------
if command_exists vulkaninfo; then
    check "vulkan_tooling" PASS "vulkaninfo presente"
else
    check "vulkan_tooling" WARN "vulkaninfo não instalado — necessário para o preflight do Unreal (07/unreal/preflight.sh)"
fi

# --- GPU NVIDIA --------------------------------------------------------------------
if has_nvidia_gpu; then
    GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
    check "gpu_presente" PASS "$GPU_NAME"
else
    check "gpu_presente" REQUIRES_GPU "nvidia-smi ausente ou sem GPU respondendo — esperado neste ambiente de desenvolvimento; obrigatório no nó real da Hostinger"
fi

# --- portas ------------------------------------------------------------------------
for port in 22 8000 5173; do
    if command_exists ss && ss -ltn 2>/dev/null | grep -q ":$port "; then
        check "porta_$port" WARN "já está em uso — confirmar que é o serviço esperado antes de subir a aplicação"
    else
        check "porta_$port" PASS "livre"
    fi
done

# --- locale ------------------------------------------------------------------------
if locale -a 2>/dev/null | grep -qi 'en_US.utf8\|C.UTF-8'; then
    check "locale" PASS "$(locale -a 2>/dev/null | grep -i 'en_US.utf8\|C.UTF-8' | head -1)"
else
    check "locale" WARN "nenhum locale UTF-8 comum encontrado — alguns instaladores (ex.: debconf) assumem isso"
fi

# --- time / NTP --------------------------------------------------------------------
if command_exists timedatectl; then
    NTP_SYNC="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)"
    if [ "$NTP_SYNC" = "yes" ]; then
        check "time_sync" PASS "NTP sincronizado"
    else
        check "time_sync" WARN "NTP não sincronizado ($NTP_SYNC) — certificados TLS e logs distribuídos dependem de hora correta"
    fi
else
    check "time_sync" WARN "timedatectl indisponível — não foi possível checar sincronização de hora"
fi

echo
log_info "Resultados completos em: $GPU_ENGINE_RESULTS_FILE"

if [ "$CRITICAL_FAIL" = "1" ]; then
    log_error "Preflight encontrou FAIL crítico. Corrija antes de rodar 01-system.sh em diante."
    exit 1
fi

log_info "Preflight concluído sem FAIL crítico."
exit 0
