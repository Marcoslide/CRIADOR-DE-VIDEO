#!/usr/bin/env bash
# system-info.sh — snapshot rápido do sistema (não instala nada, não decide PASS/FAIL,
# só informa). Útil para colar num relatório de suporte/chamado.
#
#   ./system-info.sh [--json]

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

AS_JSON=0
[ "${1:-}" = "--json" ] && AS_JSON=1

OS_PRETTY="$(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-desconhecido}")"
KERNEL="$(uname -r)"
ARCH="$(uname -m)"
CPU_MODEL="$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | sed 's/^ //')"
CPU_CORES="$(nproc --all 2>/dev/null || echo 0)"
RAM_MB="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)"
DISK_TOTAL_GB="$(df -BG --output=size / 2>/dev/null | tail -1 | tr -dc '0-9')"
DISK_TOTAL_GB="${DISK_TOTAL_GB:-0}"
DISK_AVAIL_GB="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')"
DISK_AVAIL_GB="${DISK_AVAIL_GB:-0}"
UPTIME="$(uptime -p 2>/dev/null || echo desconhecido)"

if [ "$AS_JSON" = "1" ]; then
    python3 - "$OS_PRETTY" "$KERNEL" "$ARCH" "$CPU_MODEL" "$CPU_CORES" "$RAM_MB" "$DISK_TOTAL_GB" "$DISK_AVAIL_GB" "$UPTIME" <<'PYEOF'
import json, sys
keys = ["os", "kernel", "arch", "cpu_model", "cpu_cores", "ram_mb", "disk_total_gb", "disk_avail_gb", "uptime"]
values = sys.argv[1:]
data = dict(zip(keys, values))
for k in ("cpu_cores", "ram_mb", "disk_total_gb", "disk_avail_gb"):
    data[k] = int(data[k]) if data[k].isdigit() else None
print(json.dumps(data, indent=2, ensure_ascii=False))
PYEOF
else
    cat <<EOF
Sistema:      $OS_PRETTY
Kernel:       $KERNEL
Arquitetura:  $ARCH
CPU:          $CPU_MODEL ($CPU_CORES cores)
RAM total:    ${RAM_MB} MB
Disco (/):    ${DISK_AVAIL_GB}GB livres de ${DISK_TOTAL_GB}GB
Uptime:       $UPTIME
EOF
fi
