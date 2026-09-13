#!/usr/bin/env bash
# preflight.sh — roda verify-requirements.sh e emite AUDIO2FACE_READY_FOR_INSTALL
# (seção 27 da missão).
#
#   ./preflight.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="audio2face-preflight"

"$HERE/verify-requirements.sh"

FAIL_COUNT="$(grep -c '"script":"audio2face-verify-requirements".*"status":"FAIL"' "$GPU_ENGINE_RESULTS_FILE" 2>/dev/null)"
FAIL_COUNT="${FAIL_COUNT:-0}"

echo
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "AUDIO2FACE_READY_FOR_INSTALL: YES"
    record_result "audio2face_ready_for_install" PASS "nenhum FAIL crítico"
    exit 0
else
    echo "AUDIO2FACE_READY_FOR_INSTALL: NO"
    record_result "audio2face_ready_for_install" FAIL "$FAIL_COUNT requisito(s) crítico(s) não atendido(s) — ver verify-requirements.sh acima"
    exit 1
fi
