#!/usr/bin/env bash
# 01-system.sh — usuário, timezone, updates do sistema, estrutura de diretórios do hot
# storage local (seções A6-A9 e 22 da missão).
#
#   ./01-system.sh [--dry-run]
#
# Idempotente: cada passo checa o estado atual antes de agir.

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="01-system"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

DHVF_HOME="${DHVF_HOME:-/opt/dhvf}"
DHVF_USER="${DHVF_USER:-dhf-ops}"

log_info "=== FASE A / Sistema ==="

# --- updates ------------------------------------------------------------------------
run_cmd "apt update" -- apt-get update -qq
if [ "$DRY_RUN" = "1" ]; then
    record_result "apt_update" NOT_TESTED "dry-run — simularia atualizar o índice de pacotes"
else
    record_result "apt_update" PASS "índice de pacotes atualizado"
fi
run_cmd "apt full-upgrade" -- apt-get full-upgrade -y -qq
if [ "$DRY_RUN" = "1" ]; then
    record_result "apt_upgrade" NOT_TESTED "dry-run — simularia atualizar pacotes"
else
    record_result "apt_upgrade" PASS "pacotes atualizados"
fi

if [ -f /var/run/reboot-required ]; then
    record_result "reboot_required" WARN "kernel/lib crítica atualizada — reiniciar antes de prosseguir para 02-nvidia-driver.sh"
else
    record_result "reboot_required" PASS "nenhum reboot pendente"
fi

# --- timezone -------------------------------------------------------------------------
DESIRED_TZ="${DESIRED_TZ:-America/New_York}"  # Miami
CURRENT_TZ="$(timedatectl show -p Timezone --value 2>/dev/null || echo unknown)"
if [ "$CURRENT_TZ" = "$DESIRED_TZ" ]; then
    record_result "timezone" PASS "já é $DESIRED_TZ — nada a fazer"
else
    run_cmd "definir timezone $DESIRED_TZ" -- timedatectl set-timezone "$DESIRED_TZ"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "timezone" NOT_TESTED "dry-run — simularia definir $DESIRED_TZ (era $CURRENT_TZ)"
    else
        record_result "timezone" PASS "definido para $DESIRED_TZ (era $CURRENT_TZ)"
    fi
fi

# --- usuário não-root -----------------------------------------------------------------
if id "$DHVF_USER" >/dev/null 2>&1; then
    record_result "usuario_dhf_ops" PASS "usuário '$DHVF_USER' já existe — SKIP"
else
    run_cmd "criar usuário $DHVF_USER" -- adduser --disabled-password --gecos "" "$DHVF_USER"
    run_cmd "adicionar $DHVF_USER ao grupo sudo" -- usermod -aG sudo "$DHVF_USER"
    if [ "$DRY_RUN" = "1" ]; then
        record_result "usuario_dhf_ops" NOT_TESTED "dry-run — simularia criar '$DHVF_USER' com sudo"
    else
        record_result "usuario_dhf_ops" PASS "usuário '$DHVF_USER' criado com sudo"
    fi
fi

# --- estrutura de diretórios do hot storage (seção 22) --------------------------------
SUBDIRS=(models cache assets projects renders tmp logs)
CREATED=()
for sub in "${SUBDIRS[@]}"; do
    dir="$DHVF_HOME/$sub"
    if [ -d "$dir" ]; then
        continue
    fi
    run_cmd "mkdir -p $dir" -- mkdir -p "$dir"
    CREATED+=("$sub")
done
if [ "$DRY_RUN" != "1" ]; then
    if id "$DHVF_USER" >/dev/null 2>&1; then
        run_cmd "chown -R $DHVF_USER:$DHVF_USER $DHVF_HOME" -- chown -R "$DHVF_USER:$DHVF_USER" "$DHVF_HOME"
    fi
    # 750: dono lê/escreve/executa, grupo só lê/executa, resto sem acesso — dados de
    # projeto não precisam ser world-readable num servidor multiusuário.
    run_cmd "chmod 750 $DHVF_HOME" -- chmod 750 "$DHVF_HOME"
fi
if [ "${#CREATED[@]}" -eq 0 ]; then
    record_result "hot_storage_dirs" PASS "todos os diretórios já existiam — SKIP"
elif [ "$DRY_RUN" = "1" ]; then
    record_result "hot_storage_dirs" NOT_TESTED "dry-run — simularia criar: ${CREATED[*]} (dono: $DHVF_USER, modo 750)"
else
    record_result "hot_storage_dirs" PASS "criados: ${CREATED[*]} (dono: $DHVF_USER, modo 750)"
fi

log_info "01-system.sh concluído."
