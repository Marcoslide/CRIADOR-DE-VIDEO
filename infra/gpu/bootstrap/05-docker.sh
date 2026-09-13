#!/usr/bin/env bash
# 05-docker.sh — Docker Engine + Compose plugin (repositório oficial Docker, não o pacote
# `docker.io` do Ubuntu, que costuma ficar bem mais desatualizado).
#
#   ./05-docker.sh [--dry-run]

set -uo pipefail
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="05-docker"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"

parse_common_args "$@"
require_linux
load_versions

log_info "=== FASE B / Docker Engine + Compose ==="

if command_exists docker; then
    record_result "docker_engine" PASS "SKIP — $(docker --version)"
else
    run_cmd "adicionar repositório oficial Docker" -- bash -c "
        set -e
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
        chmod a+r /etc/apt/keyrings/docker.asc
        echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-noble} stable\" \
            > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
    "
    run_cmd "instalar docker-ce + compose plugin" -- apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    if [ "$DRY_RUN" = "1" ]; then
        record_result "docker_engine" NOT_TESTED "dry-run"
    else
        record_result "docker_engine" PASS "$(docker --version 2>/dev/null)"
    fi
fi

if command_exists docker && docker compose version >/dev/null 2>&1; then
    record_result "docker_compose_plugin" PASS "$(docker compose version 2>/dev/null)"
elif [ "$DRY_RUN" != "1" ]; then
    record_result "docker_compose_plugin" WARN "plugin 'docker compose' não respondeu — checar instalação de docker-compose-plugin"
fi

# Usuário de operação no grupo docker (evita precisar de sudo para todo `docker` daqui em diante).
DHVF_USER="${DHVF_USER:-dhf-ops}"
if id "$DHVF_USER" >/dev/null 2>&1; then
    if id -nG "$DHVF_USER" 2>/dev/null | grep -qw docker; then
        record_result "docker_group" PASS "SKIP — $DHVF_USER já está no grupo docker"
    else
        run_cmd "usermod -aG docker $DHVF_USER" -- usermod -aG docker "$DHVF_USER"
        if [ "$DRY_RUN" = "1" ]; then
            record_result "docker_group" NOT_TESTED "dry-run — simularia adicionar $DHVF_USER ao grupo docker"
        else
            record_result "docker_group" PASS "$DHVF_USER adicionado ao grupo docker (relogar para efeito)"
        fi
    fi
fi

log_info "05-docker.sh concluído."
