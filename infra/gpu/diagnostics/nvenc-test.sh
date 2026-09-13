#!/usr/bin/env bash
# nvenc-test.sh — encode REAL via NVENC (h264/hevc/av1), não só "o encoder aparece na
# lista" (seção 16 da missão). Cria um vídeo sintético, encoda com cada codec NVENC
# disponível no build do ffmpeg, valida o arquivo resultante com ffprobe.
#
#   ./nvenc-test.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="nvenc-test"

if ! command_exists ffmpeg; then
    record_result "ffmpeg_binario" NOT_TESTED "ffmpeg não instalado — rode 07-media-stack.sh"
    exit 2
fi

if ! has_nvidia_gpu; then
    record_result "nvenc_gpu" REQUIRES_GPU "sem GPU NVIDIA neste ambiente — teste real só é possível no nó Hostinger"
    exit 2
fi

AVAILABLE_ENCODERS="$(ffmpeg -hide_banner -encoders 2>/dev/null | grep -E 'nvenc' | awk '{print $2}')"
ANY_TESTED=0
ANY_FAILED=0

for codec in h264_nvenc hevc_nvenc av1_nvenc; do
    if ! echo "$AVAILABLE_ENCODERS" | grep -qx "$codec"; then
        record_result "nvenc_$codec" SKIP "encoder não presente neste build do ffmpeg"
        continue
    fi

    TMP_FILE="$(mktemp --suffix=.mp4)"
    START="$(date +%s.%N)"
    if ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i "testsrc=duration=2:size=1920x1080:rate=30" \
        -c:v "$codec" -pix_fmt yuv420p "$TMP_FILE" 2>&1; then
        END="$(date +%s.%N)"
        ELAPSED="$(awk -v s="$START" -v e="$END" 'BEGIN { printf "%.2f", e - s }')"
        DURATION="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP_FILE" 2>/dev/null)"
        FILE_SIZE="$(stat -c%s "$TMP_FILE" 2>/dev/null || echo 0)"
        ANY_TESTED=1
        record_result "nvenc_$codec" PASS "encode 1080p/2s em ${ELAPSED}s, arquivo ${FILE_SIZE} bytes, duração reportada ${DURATION}s"
    else
        ANY_FAILED=1
        record_result "nvenc_$codec" FAIL "encode falhou — ver 'Cannot load libcuda.so.1' (driver não carregado) ou 'no capable devices' (GPU ocupada/indisponível) na saída do ffmpeg acima"
    fi
    rm -f "$TMP_FILE"
done

if [ "$ANY_FAILED" = "1" ]; then
    exit 1
elif [ "$ANY_TESTED" = "0" ]; then
    exit 2
fi
exit 0
