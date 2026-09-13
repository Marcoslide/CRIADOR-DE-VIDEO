#!/usr/bin/env bash
# unreal-compatibility-gate.sh — gate explícito AUDIO2FACE_UNREAL_COMPATIBILITY (seção
# 28 da missão). Não faz parte da estrutura de diretórios original pedida — adicionado
# dentro de audio2face/ (em vez de um diretório novo) porque é fundamentalmente uma
# checagem de compatibilidade *do* Audio2Face com o Unreal instalado, não o contrário;
# documentado aqui por causa da regra "se ajustar a estrutura, documente".
#
# Este teste só pode ser feito depois que AMBOS (Unreal Engine com o plugin MetaHuman e
# o container Audio2Face-3D) estiverem instalados de verdade — algo que não existe
# ainda nem no nó Hostinger (não provisionado) nem neste ambiente de desenvolvimento.
# Por isso o resultado hoje é sempre NOT_TESTED, nunca inventado.
#
#   ./unreal-compatibility-gate.sh

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$HERE/../lib/common.sh"
# shellcheck disable=SC2034  # lido por record_result() em lib/common.sh, não neste arquivo
SCRIPT_NAME="audio2face-unreal-gate"
load_versions

log_info "=== AUDIO2FACE_UNREAL_COMPATIBILITY ==="

UNREAL_INSTALLED=0
AUDIO2FACE_INSTALLED=0

if [ -x "${UNREAL_ENGINE_ROOT:-/opt/UnrealEngine}/Engine/Binaries/Linux/UnrealEditor" ]; then
    UNREAL_INSTALLED=1
fi
if command_exists docker && docker image inspect "${AUDIO2FACE_NIM_IMAGE:-nvcr.io/nvidia/ace/audio2face-3d}" >/dev/null 2>&1; then
    AUDIO2FACE_INSTALLED=1
fi

if [ "$UNREAL_INSTALLED" = "0" ] || [ "$AUDIO2FACE_INSTALLED" = "0" ]; then
    echo "AUDIO2FACE_UNREAL_COMPATIBILITY: NOT_TESTED"
    record_result "audio2face_unreal_compatibility" SKIP \
        "Unreal instalado=$UNREAL_INSTALLED, Audio2Face NIM baixado=$AUDIO2FACE_INSTALLED — teste real exige os dois presentes (versão Unreal ${UNREAL_ENGINE_VERSION:-desconhecida}, plugin MetaHuman, curvas/blendshapes exportadas do NIM, rig da MetaHuman compatível). Nada disso existe ainda neste ambiente nem no nó Hostinger (não provisionado)."
    exit 2
fi

# Quando os dois existirem de verdade, este bloco compara curvas/blendshapes exportadas
# pelo Audio2Face-3D contra os nomes de morph target esperados pelo rig da MetaHuman —
# hoje é só o esqueleto de onde essa checagem entra, não a checagem em si (que depende
# de uma MetaHuman e um resultado de inferência reais, seção 9 do AVATAR_FACTORY_SPEC.md).
echo "AUDIO2FACE_UNREAL_COMPATIBILITY: NOT_TESTED"
record_result "audio2face_unreal_compatibility" SKIP "ambos presentes, mas a checagem de blendshapes/rig ainda não está implementada — placeholder para quando um Avatar real existir"
exit 2
