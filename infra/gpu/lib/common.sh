#!/usr/bin/env bash
# common.sh — biblioteca compartilhada por todos os scripts de infra/gpu/.
#
# Não é parte da estrutura pedida originalmente (bootstrap/00-10, diagnostics/, ...) —
# adicionada para não duplicar logging/dry-run/idempotência em ~20 scripts diferentes.
# Todo script bash desta árvore começa com:
#   source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
#
# Contrato de saída: cada checagem chama `record_result NOME STATUS DETALHE`, que imprime
# uma linha legível E grava uma linha JSON em $GPU_ENGINE_RESULTS_FILE — é isso que
# 10-final-validation.sh e os relatórios em Python (services/gpu_engine) consomem depois.
# STATUS é sempre um de: PASS, WARN, FAIL, SKIP, NOT_TESTED, REQUIRES_GPU — nunca outro
# valor, e nunca PASS hardcoded sem checagem real.

set -uo pipefail

GPU_ENGINE_RESULTS_FILE="${GPU_ENGINE_RESULTS_FILE:-/tmp/gpu-engine-results.jsonl}"
DRY_RUN="${DRY_RUN:-0}"

# --- cores (desligadas se não for um terminal) ------------------------------------
if [ -t 1 ]; then
    C_RED=$'\033[31m'; C_YEL=$'\033[33m'; C_GRN=$'\033[32m'; C_BLU=$'\033[34m'; C_RST=$'\033[0m'
else
    C_RED=""; C_YEL=""; C_GRN=""; C_BLU=""; C_RST=""
fi

# --- parsing de --dry-run ----------------------------------------------------------
# Cada script chama `parse_common_args "$@"` antes de mais nada. Reconhece --dry-run e
# devolve os argumentos restantes via a variável global REMAINING_ARGS (array).
parse_common_args() {
    REMAINING_ARGS=()
    for arg in "$@"; do
        case "$arg" in
            --dry-run) DRY_RUN=1 ;;
            *) REMAINING_ARGS+=("$arg") ;;
        esac
    done
}

log_info()  { printf '%s[INFO]%s  %s\n' "$C_BLU" "$C_RST" "$*" >&2; }
log_warn()  { printf '%s[WARN]%s  %s\n' "$C_YEL" "$C_RST" "$*" >&2; }
log_error() { printf '%s[ERROR]%s %s\n' "$C_RED" "$C_RST" "$*" >&2; }

# record_result NOME STATUS DETALHE
# STATUS ∈ {PASS, WARN, FAIL, SKIP, NOT_TESTED, REQUIRES_GPU}
record_result() {
    local name="$1" status="$2" detail="${3:-}"
    local color="$C_RST"
    case "$status" in
        PASS) color="$C_GRN" ;;
        WARN) color="$C_YEL" ;;
        FAIL) color="$C_RED" ;;
    esac
    printf '%s[%s]%s %-40s %s\n' "$color" "$status" "$C_RST" "$name" "$detail"

    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    # Escapa aspas duplas e barras invertidas no detalhe antes de embutir no JSON —
    # sem isso, um `detail` contendo `"` quebraria o JSON gerado (ex.: mensagem de erro
    # de outro comando repassada como detalhe).
    local escaped_detail="${detail//\\/\\\\}"
    escaped_detail="${escaped_detail//\"/\\\"}"
    printf '{"ts":"%s","script":"%s","name":"%s","status":"%s","detail":"%s"}\n' \
        "$ts" "${SCRIPT_NAME:-$(basename "$0")}" "$name" "$status" "$escaped_detail" \
        >> "$GPU_ENGINE_RESULTS_FILE"
}

# abort_if_fail STATUS MENSAGEM — usado por preflight: aborta a sequência de bootstrap
# em qualquer FAIL crítico, mas nunca em WARN (WARN é "atenção", não "pare tudo").
abort_if_fail() {
    local status="$1" message="$2"
    if [ "$status" = "FAIL" ]; then
        log_error "Falha crítica: $message — abortando o restante do bootstrap."
        exit 1
    fi
}

# run_cmd DESCRIÇÃO -- comando args...
# Respeita --dry-run: só mostra o que seria executado, nunca executa.
run_cmd() {
    local desc="$1"; shift
    if [ "${1:-}" = "--" ]; then shift; fi
    if [ "$DRY_RUN" = "1" ]; then
        printf '%s[DRY-RUN]%s %s: %s\n' "$C_YEL" "$C_RST" "$desc" "$*"
        return 0
    fi
    log_info "$desc"
    "$@"
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

# installed_apt_version PACOTE — string vazia se não instalado.
installed_apt_version() {
    dpkg-query -W -f='${Version}' "$1" 2>/dev/null || true
}

require_linux() {
    if [ "$(uname -s)" != "Linux" ]; then
        record_result "sistema_operacional" FAIL "Este bootstrap é só para Linux (Ubuntu 24.04); detectado: $(uname -s)"
        exit 1
    fi
}

# has_nvidia_gpu — verdade só se nvidia-smi existir E rodar com sucesso. Nunca assume.
has_nvidia_gpu() {
    command_exists nvidia-smi && nvidia-smi >/dev/null 2>&1
}

# Carrega infra/gpu/config/versions.env se existir (fonte única de versões — seção 10
# da missão). Scripts individuais não devem hardcodar versão nenhuma fora daqui.
load_versions() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [ -f "$here/config/versions.env" ]; then
        # shellcheck disable=SC1091
        source "$here/config/versions.env"
    else
        log_warn "config/versions.env não encontrado — usando defaults embutidos nos scripts."
    fi
}
