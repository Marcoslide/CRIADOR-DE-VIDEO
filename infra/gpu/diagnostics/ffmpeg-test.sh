#!/usr/bin/env bash
# ffmpeg-test.sh — smoke test de FFmpeg SEM depender de GPU (encode/decode via libx264
# em CPU) — prova que o binário em si funciona antes de testar especificamente NVENC
# (isso é nvenc-test.sh, que sim precisa de GPU).
#
#   ./ffmpeg-test.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="ffmpeg-test"

if ! command_exists ffmpeg; then
    record_result "ffmpeg_binario" NOT_TESTED "ffmpeg não instalado — rode 07-media-stack.sh"
    exit 2
fi
if ! command_exists ffprobe; then
    record_result "ffprobe_binario" NOT_TESTED "ffprobe não instalado (normalmente vem junto do pacote ffmpeg)"
    exit 2
fi

record_result "ffmpeg_binario" PASS "$(ffmpeg -version 2>/dev/null | head -1)"

TMP_FILE="$(mktemp --suffix=.mp4)"
trap 'rm -f "$TMP_FILE"' EXIT

if ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc=duration=2:size=1280x720:rate=30" \
    -c:v libx264 -pix_fmt yuv420p "$TMP_FILE" 2>&1; then
    record_result "ffmpeg_encode_cpu" PASS "encode libx264 de 2s/720p concluído"
else
    record_result "ffmpeg_encode_cpu" FAIL "encode via libx264 falhou — problema no build do ffmpeg, não relacionado a GPU"
    exit 1
fi

DURATION="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP_FILE" 2>/dev/null)"
if awk -v d="$DURATION" 'BEGIN { exit !(d >= 1.8 && d <= 2.2) }' 2>/dev/null; then
    record_result "ffprobe_valida_arquivo" PASS "duração reportada: ${DURATION}s (esperado ~2s)"
else
    record_result "ffprobe_valida_arquivo" FAIL "duração inesperada: ${DURATION:-vazia} (esperado ~2s) — arquivo pode estar corrompido"
    exit 1
fi

log_info "ffmpeg-test.sh: PASS. Para o teste específico de NVENC (precisa de GPU): ./nvenc-test.sh"
exit 0
