#!/usr/bin/env bash
# 09-monitoring.sh — ferramentas de observação (seção F da missão). Tudo aqui é apt
# padrão — nenhum serviço externo pago nesta etapa inicial (dcgm-exporter/Prometheus
# ficam para quando o volume de jobs justificar, ver infra/gpu/README.md).
#
#   ./09-monitoring.sh [--dry-run]

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="09-monitoring"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

log_info "=== FASE F / Monitoramento ==="

PACKAGES=(htop dstat sysstat lm-sensors)
MISSING=()
for pkg in "${PACKAGES[@]}"; do
    if dpkg -l 2>/dev/null | grep -qE "^ii\s+$pkg\s"; then
        continue
    fi
    MISSING+=("$pkg")
done

if [ "${#MISSING[@]}" -eq 0 ]; then
    record_result "monitoring_pacotes" PASS "SKIP — ${PACKAGES[*]} já instalados"
else
    run_cmd "instalar ${MISSING[*]}" -- apt-get install -y -qq "${MISSING[@]}"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "monitoring_pacotes" NOT_TESTED "dry-run"
    else
        record_result "monitoring_pacotes" PASS "instalados: ${MISSING[*]}"
    fi
fi

# habilita coleta de estatísticas do sysstat (sar) — vem desligado por padrão no Ubuntu
if [ -f /etc/default/sysstat ] && grep -q '^ENABLED="true"' /etc/default/sysstat 2>/dev/null; then
    record_result "sysstat_enabled" PASS "SKIP — já habilitado"
else
    run_cmd "habilitar sysstat" -- sed -i 's/^ENABLED=.*/ENABLED="true"/' /etc/default/sysstat
    run_cmd "reiniciar sysstat" -- systemctl restart sysstat
    if [ "$DRY_RUN" = "1" ]; then
        record_result "sysstat_enabled" NOT_TESTED "dry-run — simularia habilitar sysstat"
    else
        record_result "sysstat_enabled" PASS "habilitado"
    fi
fi

if [ "$DRY_RUN" != "1" ] && has_nvidia_gpu; then
    record_result "nvidia_smi_dmon" PASS "disponível (nvidia-smi dmon) — usado pelo NVENC/GPU util no telemetry.py"
elif [ "$DRY_RUN" != "1" ]; then
    record_result "nvidia_smi_dmon" REQUIRES_GPU "sem GPU neste ambiente"
fi

log_info "09-monitoring.sh concluído. Telemetria estruturada real: services/gpu_engine (dhf_gpu_engine.telemetry)."
