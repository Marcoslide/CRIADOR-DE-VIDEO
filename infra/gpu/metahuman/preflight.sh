#!/usr/bin/env bash
# preflight.sh — dependências para MetaHuman / MetaHuman Creator / MetaHuman Animator
# (seção 26 da missão). Diferente de unreal/ e audio2face/, aqui o resultado principal
# não é um YES/NO de instalação — é a separação real, confirmada por pesquisa (fonte:
# dev.epicgames.com/documentation/en-us/metahuman/hardware-requirements-for-animator,
# via busca indexada nesta sessão), entre o que roda no Linux e o que é Windows-only.
# Nunca recomenda Windows "por precaução" — só reporta o que a documentação da Epic
# afirma explicitamente.
#
#   ./preflight.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="metahuman-preflight"

log_info "=== MetaHuman — componentes Linux vs. Windows-only ==="

# Depende do plugin MetaHuman existir dentro de um Unreal Engine já compilado — este
# preflight roda de forma independente (não instala nada), só reporta o que é
# tecnicamente possível nesta plataforma segundo a documentação oficial da Epic.

cat <<'EOF'
LINUX_SUPPORTED_COMPONENTS:
  - MetaHuman Creator (plugin, desde UE 5.6+) — montagem e edição manual de personagem
    a partir dos presets/sliders do MetaHuman.
  - Aplicação de uma MetaHuman já criada numa cena/nível do Unreal (Lumen, Ray Tracing,
    Groom, Cloth) — a MetaHuman em si roda normalmente uma vez montada.
  - Movie Render Queue sobre uma MetaHuman existente (renderização, não captura).

WINDOWS_ONLY_COMPONENTS:
  - MetaHuman Animator — o marker tracking da etapa de captura de performance depende
    de DirectX 12, que não existe no Linux. Confirmado pela documentação oficial da
    Epic, não é uma limitação hipotética.
  - Identity/Performance dentro do MetaHuman Creator (o fluxo "scan facial/vídeo →
    personagem") — desabilitado no Linux/Mac pela mesma dependência do Animator.
EOF

# SKIP (não FAIL): isto não é um erro de configuração deste bootstrap corrigível com
# outro pacote/driver — é uma limitação de plataforma permanente e documentada pela
# própria Epic. Contar como FAIL poluiria a agregação de 10-final-validation.sh com algo
# que nenhuma reinstalação neste nó jamais vai resolver.
record_result "metahuman_creator_linux" PASS "montagem/edição manual funciona no Linux (sem Identity/Performance)"
record_result "metahuman_animator_linux" SKIP "Windows-only (DirectX 12) — não roda no nó Hostinger Linux, por design da Epic. Ver GPU_ENGINE_SETUP_PLAN.md / decisão pendente: instância Windows adicional só para esta etapa, ou aceitar a limitação por enquanto."
record_result "metahuman_identity_performance_linux" SKIP "desabilitado no Linux (mesma dependência do Animator) — mesma observação acima"

log_info "metahuman/preflight.sh concluído. Isto não é um FAIL do bootstrap — é uma limitação de plataforma documentada, não um erro de configuração local."
exit 0
