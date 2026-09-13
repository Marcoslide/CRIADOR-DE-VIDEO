#!/usr/bin/env bash
# gpu-info.sh — detecta e imprime tudo que o driver NVIDIA sabe sobre a GPU. Nunca
# inventa um valor: sem nvidia-smi, imprime REQUIRES_GPU e sai com código 2 (distinto de
# 1, que é erro de verdade) — permite scripts chamadores diferenciarem "sem GPU" de
# "GPU presente mas algo quebrou".
#
#   ./gpu-info.sh [--json]

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

AS_JSON=0
[ "${1:-}" = "--json" ] && AS_JSON=1

if ! command_exists nvidia-smi; then
    if [ "$AS_JSON" = "1" ]; then
        echo '{"status": "REQUIRES_GPU", "detail": "nvidia-smi não encontrado no PATH"}'
    else
        log_warn "REQUIRES_GPU — nvidia-smi não encontrado no PATH. Normal em ambiente de desenvolvimento sem GPU; obrigatório no nó Hostinger."
    fi
    exit 2
fi

QUERY="name,driver_version,memory.total,memory.free,memory.used,temperature.gpu,power.draw,power.limit,utilization.gpu,utilization.memory,compute_cap"
RAW="$(nvidia-smi --query-gpu="$QUERY" --format=csv,noheader,nounits 2>&1)"
RC=$?

if [ $RC -ne 0 ]; then
    if [ "$AS_JSON" = "1" ]; then
        python3 -c "import json,sys; print(json.dumps({'status': 'FAIL', 'detail': sys.argv[1]}))" "$RAW"
    else
        log_error "FAIL — nvidia-smi retornou erro (driver instalado mas GPU não responde): $RAW"
    fi
    exit 1
fi

# nvidia-smi separa campos com ", " — normalizamos removendo o espaço extra.
IFS=',' read -r NAME DRIVER VRAM_TOTAL VRAM_FREE VRAM_USED TEMP POWER_DRAW POWER_LIMIT UTIL_GPU UTIL_MEM COMPUTE_CAP <<< "$RAW"
trim() { echo "$1" | sed 's/^ *//;s/ *$//'; }
NAME="$(trim "$NAME")"; DRIVER="$(trim "$DRIVER")"; VRAM_TOTAL="$(trim "$VRAM_TOTAL")"
VRAM_FREE="$(trim "$VRAM_FREE")"; VRAM_USED="$(trim "$VRAM_USED")"; TEMP="$(trim "$TEMP")"
POWER_DRAW="$(trim "$POWER_DRAW")"; POWER_LIMIT="$(trim "$POWER_LIMIT")"
UTIL_GPU="$(trim "$UTIL_GPU")"; UTIL_MEM="$(trim "$UTIL_MEM")"; COMPUTE_CAP="$(trim "$COMPUTE_CAP")"

# Encoder/decoder utilization não vem de --query-gpu em todas as versões de driver —
# tenta um campo dedicado; se "[Not Supported]", reporta null em vez de inventar 0.
ENC_UTIL="$(nvidia-smi --query-gpu=utilization.encoder --format=csv,noheader,nounits 2>/dev/null | head -1 || true)"
DEC_UTIL="$(nvidia-smi --query-gpu=utilization.decoder --format=csv,noheader,nounits 2>/dev/null | head -1 || true)"

if [ "$AS_JSON" = "1" ]; then
    python3 - "$NAME" "$DRIVER" "$VRAM_TOTAL" "$VRAM_FREE" "$VRAM_USED" "$TEMP" "$POWER_DRAW" "$POWER_LIMIT" "$UTIL_GPU" "$UTIL_MEM" "$COMPUTE_CAP" "$ENC_UTIL" "$DEC_UTIL" <<'PYEOF'
import json, sys

def as_float(v):
    v = (v or "").strip()
    if not v or "Not Supported" in v:
        return None
    try:
        return float(v)
    except ValueError:
        return None

(name, driver, vram_total, vram_free, vram_used, temp, power_draw, power_limit,
 util_gpu, util_mem, compute_cap, enc_util, dec_util) = sys.argv[1:14]

print(json.dumps({
    "status": "PASS",
    "device_name": name,
    "driver_version": driver,
    "cuda_capability": compute_cap,
    "vram_total_mb": as_float(vram_total),
    "vram_free_mb": as_float(vram_free),
    "vram_used_mb": as_float(vram_used),
    "temperature_c": as_float(temp),
    "power_draw_w": as_float(power_draw),
    "power_limit_w": as_float(power_limit),
    "utilization_gpu_pct": as_float(util_gpu),
    "utilization_memory_pct": as_float(util_mem),
    "encoder_utilization_pct": as_float(enc_util),
    "decoder_utilization_pct": as_float(dec_util),
}, indent=2, ensure_ascii=False))
PYEOF
else
    cat <<EOF
GPU:                $NAME
Driver:             $DRIVER
Compute capability: $COMPUTE_CAP
VRAM:               ${VRAM_USED}MB usados / ${VRAM_TOTAL}MB total (${VRAM_FREE}MB livres)
Temperatura:        ${TEMP}°C
Power:              ${POWER_DRAW}W / ${POWER_LIMIT}W limite
Utilização GPU:     ${UTIL_GPU}%
Utilização memória: ${UTIL_MEM}%
Utilização encoder: ${ENC_UTIL:-não suportado pelo driver}%
Utilização decoder: ${DEC_UTIL:-não suportado pelo driver}%
EOF
fi
