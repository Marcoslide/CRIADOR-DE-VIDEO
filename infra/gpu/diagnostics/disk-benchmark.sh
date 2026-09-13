#!/usr/bin/env bash
# disk-benchmark.sh — read/write/random IO básico + espaço livre (seção 24 da missão).
# Usa `dd` (sempre disponível) para read/write sequencial; `fio` se estiver instalado,
# para random IO — sem fio, reporta essa parte como SKIP (não finge um número).
#
#   ./disk-benchmark.sh [caminho_de_teste]

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="disk-benchmark"

TEST_DIR="${1:-${DHVF_TMP_DIR:-/tmp}}"
mkdir -p "$TEST_DIR"
TEST_FILE="$TEST_DIR/.gpu-engine-disk-benchmark"
trap 'rm -f "$TEST_FILE"' EXIT

# --- espaço livre --------------------------------------------------------------------
AVAIL_PCT="$(df --output=pcent "$TEST_DIR" 2>/dev/null | tail -1 | tr -dc '0-9')"
FREE_PCT=$((100 - ${AVAIL_PCT:-0}))
WARN_THRESHOLD="${DISK_WARNING_FREE_PCT:-20}"
CRIT_THRESHOLD="${DISK_CRITICAL_FREE_PCT:-8}"
if [ "$FREE_PCT" -lt "$CRIT_THRESHOLD" ]; then
    record_result "disk_free_pct" FAIL "${FREE_PCT}% livre em $TEST_DIR — abaixo do crítico (${CRIT_THRESHOLD}%). Nunca deixar um render consumir o disco inteiro."
elif [ "$FREE_PCT" -lt "$WARN_THRESHOLD" ]; then
    record_result "disk_free_pct" WARN "${FREE_PCT}% livre em $TEST_DIR — abaixo do aviso (${WARN_THRESHOLD}%)"
else
    record_result "disk_free_pct" PASS "${FREE_PCT}% livre em $TEST_DIR"
fi

# --- write sequencial (dd) ------------------------------------------------------------
WRITE_OUTPUT="$(dd if=/dev/zero of="$TEST_FILE" bs=1M count=256 oflag=direct 2>&1 || dd if=/dev/zero of="$TEST_FILE" bs=1M count=256 2>&1)"
WRITE_SPEED="$(echo "$WRITE_OUTPUT" | grep -oE '[0-9.]+ [MG]B/s' | tail -1)"
if [ -n "$WRITE_SPEED" ]; then
    record_result "disk_write_seq" PASS "$WRITE_SPEED (256MB)"
else
    record_result "disk_write_seq" WARN "não foi possível extrair velocidade da saída do dd: $WRITE_OUTPUT"
fi

# --- read sequencial (dd, com drop de cache quando possível) --------------------------
if [ "$(id -u)" = "0" ] && [ -w /proc/sys/vm/drop_caches ]; then
    sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
fi
READ_OUTPUT="$(dd if="$TEST_FILE" of=/dev/null bs=1M 2>&1)"
READ_SPEED="$(echo "$READ_OUTPUT" | grep -oE '[0-9.]+ [MG]B/s' | tail -1)"
if [ -n "$READ_SPEED" ]; then
    record_result "disk_read_seq" PASS "$READ_SPEED (256MB, cache pode não ter sido dropado — número otimista se não rodou como root)"
else
    record_result "disk_read_seq" WARN "não foi possível extrair velocidade da saída do dd: $READ_OUTPUT"
fi

# --- random IO (fio, opcional) -------------------------------------------------------
if command_exists fio; then
    FIO_OUTPUT="$(fio --name=randrw_test --directory="$TEST_DIR" --size=64M --rw=randrw \
        --bs=4k --runtime=5 --time_based --group_reporting --minimal 2>/dev/null || true)"
    if [ -n "$FIO_OUTPUT" ]; then
        record_result "disk_random_io" PASS "fio executado — ver detalhes em modo --minimal no log completo"
    else
        record_result "disk_random_io" WARN "fio instalado mas não retornou saída utilizável"
    fi
else
    record_result "disk_random_io" SKIP "fio não instalado — random IO não medido (apt install fio para habilitar)"
fi

log_info "disk-benchmark.sh concluído."
