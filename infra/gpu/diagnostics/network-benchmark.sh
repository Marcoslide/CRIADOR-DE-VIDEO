#!/usr/bin/env bash
# network-benchmark.sh — latência/throughput básicos até os hosts que o pipeline
# realmente usa (registries, NGC, GitHub) — não um speedtest genérico. Útil para
# diagnosticar "download lento de modelo" vs. "servidor de origem lento".
#
#   ./network-benchmark.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="network-benchmark"

HOSTS=(
    "developer.download.nvidia.com"
    "github.com"
    "download.pytorch.org"
)
ANY_FAIL=0

for host in "${HOSTS[@]}"; do
    if ! command_exists curl; then
        record_result "rede_$host" SKIP "curl não disponível"
        continue
    fi
    # IMPORTANTE: não usar `curl ... || echo fallback` aqui — com -w, o curl imprime os
    # timings parciais que já coletou ANTES de retornar erro (ex.: exit 56 =
    # CURLE_RECV_ERROR, comum com o proxy deste ambiente), e o fallback rodaria por
    # cima dessa saída parcial dentro da mesma substituição de comando, concatenando
    # os dois e corrompendo o parsing (bug real encontrado rodando este script).
    TIMING="$(curl -o /dev/null -s -w '%{time_connect},%{time_starttransfer},%{http_code}' \
        --max-time 8 "https://$host" 2>/dev/null)"
    CURL_RC=$?
    IFS=',' read -r CONNECT_S TTFB_S HTTP_CODE <<< "$TIMING"
    if [ "$CURL_RC" -eq 0 ] && [ -n "$HTTP_CODE" ] && [ "$HTTP_CODE" != "000" ]; then
        record_result "rede_$host" PASS "conectou em ${CONNECT_S}s, primeiro byte em ${TTFB_S}s, HTTP $HTTP_CODE"
    else
        record_result "rede_$host" FAIL "não foi possível conectar a $host (curl exit=$CURL_RC, http_code=${HTTP_CODE:-vazio})"
        ANY_FAIL=1
    fi
done

log_info "network-benchmark.sh concluído."
# Não-crítico por natureza (informativo) — mas o exit code reflete o resultado real
# para quem quiser usar isto em um pipeline de CI/preflight mais rígido no futuro.
[ "$ANY_FAIL" = "1" ] && exit 1
exit 0
