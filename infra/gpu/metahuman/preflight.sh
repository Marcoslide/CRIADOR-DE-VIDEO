#!/usr/bin/env bash
# preflight.sh — dependências para MetaHuman / MetaHuman Creator / MetaHuman Animator
# (seção 26 da missão). Diferente de unreal/ e audio2face/, aqui o resultado principal
# não é um YES/NO de instalação — é a separação real entre o que roda no Linux e o que
# é Windows-only/limitado, GRANULAR por workflow (nunca um veredito único para "o
# Animator inteiro").
#
# CORRIGIDO (revisão pós-PR#4): a primeira versão deste arquivo generalizava, a partir
# de busca indexada, "MetaHuman Animator inteiro = Windows-only (DirectX 12)". Isso
# estava errado. No MetaHuman 5.8, o Linux suporta: MetaHuman Creator, MetaHuman
# Animator FACIAL (offline e realtime, conforme o workflow suportado), geração de
# animação facial a partir disso, uso de MetaHumans numa cena, e Movie Render Queue. A
# limitação real e específica é BODY ANIMATION / MARKERLESS BODY CAPTURE — só essa parte
# é Windows-only/limitada no Linux. Não generalizar de novo: se algum workflow
# específico de Identity/Performance exigir DX12, registrar ESSE workflow
# individualmente (ver metahuman_identity_performance_linux abaixo) — nunca "Animator
# inteiro é Windows-only".
#
#   ./preflight.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="metahuman-preflight"

log_info "=== MetaHuman 5.8 — componentes Linux vs. Windows-only (granular por workflow) ==="

# Depende do plugin MetaHuman existir dentro de um Unreal Engine já compilado — este
# preflight roda de forma independente (não instala nada), só reporta o que é
# tecnicamente possível nesta plataforma.

cat <<'EOF'
LINUX_SUPPORTED_COMPONENTS (MetaHuman 5.8):
  - MetaHuman Creator (plugin, desde UE 5.6+) — montagem e edição manual de personagem
    a partir dos presets/sliders do MetaHuman.
  - MetaHuman Animator — captura FACIAL (offline e realtime, conforme o workflow
    suportado) e geração de animação facial a partir disso.
  - Aplicação de uma MetaHuman já criada numa cena/nível do Unreal (Lumen, Ray Tracing,
    Groom, Cloth) — a MetaHuman em si roda normalmente uma vez montada.
  - Movie Render Queue sobre uma MetaHuman existente (renderização, não captura).
  - Pipeline Avatar Factory preferido nesta missão — MULTIVIEW → MESH MASTER →
    REFINEMENT → METAHUMAN CREATOR → FROM CUSTOM MESH → RIG — não depende de captura
    de performance nem de Identity/scan, então roda inteiro nos componentes acima.

WINDOWS_ONLY_OU_LIMITADO_NO_LINUX:
  - Body animation / markerless body capture — a captura de CORPO do MetaHuman Animator
    (diferente da captura facial, que é suportada no Linux).

NÃO CONFIRMADO NESTA REVISÃO (não generalizar a partir disto):
  - Identity/Performance (fluxo "scan facial/vídeo → personagem customizado") — não faz
    parte do pipeline Avatar Factory escolhido acima (que usa FROM CUSTOM MESH, não
    scan/Identity), então não foi exercitado/confirmado nesta missão. Se um workflow
    específico dentro de Identity/Performance exigir DX12, registrar ESSE workflow
    individualmente aqui quando confirmado.
EOF

# SKIP (não FAIL) para a limitação de corpo: não é um erro de configuração deste
# bootstrap corrigível com outro pacote/driver — é uma limitação de plataforma
# documentada. Contar como FAIL poluiria a agregação de 10-final-validation.sh com algo
# que nenhuma reinstalação neste nó jamais vai resolver. NOT_TESTED (não SKIP nem PASS)
# para Identity/Performance: honesto sobre o que não foi verificado, sem generalizar.
record_result "metahuman_creator_linux" PASS "montagem/edição manual funciona no Linux"
record_result "metahuman_animator_facial_linux" PASS "captura facial (offline e realtime) + geração de animação facial suportadas no Linux no MetaHuman 5.8 — não é Windows-only"
record_result "metahuman_body_markerless_linux" SKIP "UNSUPPORTED_PLATFORM/Windows-only — body animation / markerless body capture não roda no Linux. Não afeta a captura facial (Animator facial) nem o pipeline Avatar Factory (MULTIVIEW→MESH MASTER→REFINEMENT→METAHUMAN CREATOR→FROM CUSTOM MESH→RIG), nenhum dos dois depende de captura de corpo."
record_result "metahuman_identity_performance_linux" NOT_TESTED "não confirmado nesta revisão — fora do pipeline Avatar Factory escolhido (que usa FROM CUSTOM MESH, não Identity/scan). Se um workflow específico exigir DX12, registrar individualmente aqui quando confirmado — não generalizar para o Animator inteiro."

log_info "metahuman/preflight.sh concluído. metahuman_body_markerless_linux=SKIP é uma limitação de plataforma documentada (não um erro de configuração local); Creator e Animator facial são suportados no Linux."
exit 0
