"""Árvore oficial de pastas do Google Drive.

O bootstrap cria idempotentemente as 18 pastas sob a root marcada pelo aplicativo. As
operações normais nunca renomeiam nem apagam essas pastas. Ver docs/STORAGE_GOOGLE_DRIVE.md.
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

# Áreas onde delete() sem allow_permanent=True é permitido (e ali, move para a
# lixeira do Drive, nunca exclusão definitiva). ``_integration_tests`` é uma pasta
# interna criada sob a root apenas quando a suíte real é executada; ela não integra
# as 18 pastas oficiais.
SCRATCH_PREFIX = "02_SISTEMA_STORAGE/_tmp"
INTEGRATION_TESTS_PREFIX = "_integration_tests"
SAFE_TRASH_PREFIXES = (SCRATCH_PREFIX, INTEGRATION_TESTS_PREFIX)


def validate_tree(found_names: list[str]) -> TreeValidationResult:
    found_set = set(found_names)
    expected_set = set(OFFICIAL_TOP_LEVEL_FOLDERS)
    missing = [name for name in OFFICIAL_TOP_LEVEL_FOLDERS if name not in found_set]
    # A pasta interna de integração é conhecida e não representa drift da árvore
    # oficial. Pastas realmente desconhecidas continuam aparecendo no diagnóstico.
    unexpected = sorted(found_set - expected_set - {INTEGRATION_TESTS_PREFIX})
    return TreeValidationResult(
        expected=OFFICIAL_TOP_LEVEL_FOLDERS,
        found=sorted(found_set & expected_set),
        missing=missing,
        unexpected=unexpected,
        valid=not missing,
    )


def is_within_scratch(remote_path: str) -> bool:
    normalized = remote_path.strip("/")
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in SAFE_TRASH_PREFIXES
    )
