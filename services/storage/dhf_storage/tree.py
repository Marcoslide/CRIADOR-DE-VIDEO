"""Árvore oficial de pastas do Google Drive.

Criada manualmente pelo usuário — o provider NUNCA cria, renomeia ou apaga estas 18 pastas
de topo, só descobre por nome e valida que existem. Ver docs/STORAGE_GOOGLE_DRIVE.md.
"""

from dhf_schemas.storage import TreeValidationResult

OFFICIAL_TOP_LEVEL_FOLDERS: list[str] = [
    "00_PROJETO_GOVERNANCA",
    "01_INFRA",
    "02_SISTEMA_STORAGE",
    "03_AVATAR_IDENTITY_FOTOS",
    "04_DIGITAL_DOUBLE_MESH_RIG",
    "05_REALISMO_LOOKDEV",
    "06_FACE_PERFORMANCE",
    "07_VOICE_DNA",
    "08_MOTION_DNA_CORPO_MAOS",
    "09_PRODUTO_PRODUCT_3D",
    "10_DIRECTOR_AI_BRAINS",
    "11_CENARIOS_CAMERA_LUZ",
    "12_VIDEO_PIPELINE_UNREAL_RENDER",
    "13_EDICAO_REMOTION_FFMPEG",
    "14_QUALITY_GATE_TESTES",
    "15_MVP_VIDEO_30S",
    "16_ESCALA_CANAIS_ARTISTAS",
    "17_FUTURO_LIVE",
]

# Única área onde delete() sem allow_permanent=True é permitido (e ali, move para a
# lixeira do Drive, nunca exclusão definitiva). Fora daqui, delete() exige
# allow_permanent=True e então é definitivo. Ver GoogleDriveStorageProvider.delete().
SCRATCH_PREFIX = "02_SISTEMA_STORAGE/_tmp"


def validate_tree(found_names: list[str]) -> TreeValidationResult:
    found_set = set(found_names)
    expected_set = set(OFFICIAL_TOP_LEVEL_FOLDERS)
    missing = [name for name in OFFICIAL_TOP_LEVEL_FOLDERS if name not in found_set]
    unexpected = sorted(found_set - expected_set)
    return TreeValidationResult(
        expected=OFFICIAL_TOP_LEVEL_FOLDERS,
        found=sorted(found_set & expected_set),
        missing=missing,
        unexpected=unexpected,
        valid=not missing,
    )


def is_within_scratch(remote_path: str) -> bool:
    normalized = remote_path.strip("/")
    return normalized == SCRATCH_PREFIX or normalized.startswith(SCRATCH_PREFIX + "/")
