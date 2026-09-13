#!/usr/bin/env bash
# 07-media-stack.sh — FFmpeg (NVENC habilitado via pacote apt padrão do Ubuntu 24.04 —
# suficiente para a RTX 4090, ver infra/gpu/README.md; diferente da RTX 5090/Blackwell,
# que precisaria recompilar para features novas do SDK 13.0).
#
#   ./07-media-stack.sh [--dry-run]

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="07-media-stack"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

log_info "=== FASE C / Media stack (FFmpeg/NVENC) ==="

if command_exists ffmpeg; then
    record_result "ffmpeg_pacote" PASS "SKIP — $(ffmpeg -version 2>/dev/null | head -1)"
else
    run_cmd "instalar ffmpeg" -- apt-get install -y -qq ffmpeg
    if [ "$DRY_RUN" = "1" ]; then
        record_result "ffmpeg_pacote" NOT_TESTED "dry-run"
    else
        record_result "ffmpeg_pacote" PASS "$(ffmpeg -version 2>/dev/null | head -1)"
    fi
fi

if [ "$DRY_RUN" != "1" ] && command_exists ffmpeg; then
    ENCODERS="$(ffmpeg -hide_banner -encoders 2>/dev/null | grep -E 'nvenc' || true)"
    for codec in h264_nvenc hevc_nvenc av1_nvenc; do
        if echo "$ENCODERS" | grep -q "$codec"; then
            record_result "nvenc_$codec" PASS "encoder presente no build do FFmpeg"
        else
            record_result "nvenc_$codec" WARN "encoder ausente — este build de FFmpeg não tem $codec (recompilar contra nv-codec-headers se for crítico)"
        fi
    done
fi

log_info "07-media-stack.sh concluído. Teste funcional real (precisa de GPU): infra/gpu/diagnostics/nvenc-test.sh"
