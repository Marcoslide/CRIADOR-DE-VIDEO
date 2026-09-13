"""Vocabulário fechado do Avatar Factory Control Plane. Cada enum aqui é literal — os
valores definidos na missão, sem adição nem omissão silenciosa (mesmo princípio de
`dhf_avatars.schemas.AvatarStatus`)."""

from enum import StrEnum

from dhf_avatars.schemas import AvatarStatus


class IdentityLockStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class ReferenceAssetCategory(StrEnum):
    # --- famílias 360° (usam o campo `angle`, 0-350 em passos de 10) -------------------
    HEAD_360 = "head_360"
    HALF_BODY_360 = "half_body_360"
    FULL_BODY_360 = "full_body_360"

    # --- referências especializadas -----------------------------------------------------
    FACE_FRONT_NEUTRAL = "face_front_neutral"
    FACE_LEFT_PROFILE = "face_left_profile"
    FACE_RIGHT_PROFILE = "face_right_profile"
    FACE_3Q_LEFT = "face_3q_left"
    FACE_3Q_RIGHT = "face_3q_right"
    EYES_CLOSE = "eyes_close"
    LEFT_EYE_CLOSE = "left_eye_close"
    RIGHT_EYE_CLOSE = "right_eye_close"
    IRIS_REFERENCE = "iris_reference"
    SKIN_CLOSE = "skin_close"
    PORES_REFERENCE = "pores_reference"
    MOUTH_CLOSED = "mouth_closed"
    MOUTH_OPEN = "mouth_open"
    TEETH_FRONT = "teeth_front"
    TEETH_SIDE = "teeth_side"
    GUMS = "gums"
    TONGUE = "tongue"
    EAR_LEFT = "ear_left"
    EAR_RIGHT = "ear_right"
    HAIRLINE_FRONT = "hairline_front"
    HAIRLINE_LEFT = "hairline_left"
    HAIRLINE_RIGHT = "hairline_right"
    HAIR_BACK = "hair_back"
    HAND_LEFT_FRONT = "hand_left_front"
    HAND_LEFT_BACK = "hand_left_back"
    HAND_RIGHT_FRONT = "hand_right_front"
    HAND_RIGHT_BACK = "hand_right_back"
    NAILS = "nails"
    FEET = "feet"
    BODY_FRONT = "body_front"
    BODY_BACK = "body_back"
    BODY_LEFT = "body_left"
    BODY_RIGHT = "body_right"

    # --- expression master set -----------------------------------------------------------
    EXPR_NEUTRAL = "expr_neutral"
    EXPR_SMALL_SMILE = "expr_small_smile"
    EXPR_FULL_SMILE = "expr_full_smile"
    EXPR_SERIOUS = "expr_serious"
    EXPR_CONCERNED = "expr_concerned"
    EXPR_SURPRISED = "expr_surprised"
    EXPR_ANGRY_LIGHT = "expr_angry_light"
    EXPR_SAD_LIGHT = "expr_sad_light"
    EXPR_EYES_CLOSED = "expr_eyes_closed"
    EXPR_BLINK_MID = "expr_blink_mid"
    EXPR_MOUTH_A = "expr_mouth_a"
    EXPR_MOUTH_E = "expr_mouth_e"
    EXPR_MOUTH_I = "expr_mouth_i"
    EXPR_MOUTH_O = "expr_mouth_o"
    EXPR_MOUTH_U = "expr_mouth_u"
    EXPR_JAW_OPEN = "expr_jaw_open"
    EXPR_CHEEK_RAISE = "expr_cheek_raise"
    EXPR_BROW_UP = "expr_brow_up"
    EXPR_BROW_DOWN = "expr_brow_down"


# Ângulos exigidos para cada família 360° — 36 posições, passo de 10° (seções 8-10).
REQUIRED_ANGLES: tuple[int, ...] = tuple(range(0, 360, 10))

ANGLE_360_CATEGORIES: frozenset[ReferenceAssetCategory] = frozenset(
    {
        ReferenceAssetCategory.HEAD_360,
        ReferenceAssetCategory.HALF_BODY_360,
        ReferenceAssetCategory.FULL_BODY_360,
    }
)

SPECIALIZED_CATEGORIES: frozenset[ReferenceAssetCategory] = frozenset(
    {
        ReferenceAssetCategory.FACE_FRONT_NEUTRAL,
        ReferenceAssetCategory.FACE_LEFT_PROFILE,
        ReferenceAssetCategory.FACE_RIGHT_PROFILE,
        ReferenceAssetCategory.FACE_3Q_LEFT,
        ReferenceAssetCategory.FACE_3Q_RIGHT,
        ReferenceAssetCategory.EYES_CLOSE,
        ReferenceAssetCategory.LEFT_EYE_CLOSE,
        ReferenceAssetCategory.RIGHT_EYE_CLOSE,
        ReferenceAssetCategory.IRIS_REFERENCE,
        ReferenceAssetCategory.SKIN_CLOSE,
        ReferenceAssetCategory.PORES_REFERENCE,
        ReferenceAssetCategory.MOUTH_CLOSED,
        ReferenceAssetCategory.MOUTH_OPEN,
        ReferenceAssetCategory.TEETH_FRONT,
        ReferenceAssetCategory.TEETH_SIDE,
        ReferenceAssetCategory.GUMS,
        ReferenceAssetCategory.TONGUE,
        ReferenceAssetCategory.EAR_LEFT,
        ReferenceAssetCategory.EAR_RIGHT,
        ReferenceAssetCategory.HAIRLINE_FRONT,
        ReferenceAssetCategory.HAIRLINE_LEFT,
        ReferenceAssetCategory.HAIRLINE_RIGHT,
        ReferenceAssetCategory.HAIR_BACK,
        ReferenceAssetCategory.HAND_LEFT_FRONT,
        ReferenceAssetCategory.HAND_LEFT_BACK,
        ReferenceAssetCategory.HAND_RIGHT_FRONT,
        ReferenceAssetCategory.HAND_RIGHT_BACK,
        ReferenceAssetCategory.NAILS,
        ReferenceAssetCategory.FEET,
        ReferenceAssetCategory.BODY_FRONT,
        ReferenceAssetCategory.BODY_BACK,
        ReferenceAssetCategory.BODY_LEFT,
        ReferenceAssetCategory.BODY_RIGHT,
    }
)

EXPRESSION_CATEGORIES: frozenset[ReferenceAssetCategory] = frozenset(
    {
        ReferenceAssetCategory.EXPR_NEUTRAL,
        ReferenceAssetCategory.EXPR_SMALL_SMILE,
        ReferenceAssetCategory.EXPR_FULL_SMILE,
        ReferenceAssetCategory.EXPR_SERIOUS,
        ReferenceAssetCategory.EXPR_CONCERNED,
        ReferenceAssetCategory.EXPR_SURPRISED,
        ReferenceAssetCategory.EXPR_ANGRY_LIGHT,
        ReferenceAssetCategory.EXPR_SAD_LIGHT,
        ReferenceAssetCategory.EXPR_EYES_CLOSED,
        ReferenceAssetCategory.EXPR_BLINK_MID,
        ReferenceAssetCategory.EXPR_MOUTH_A,
        ReferenceAssetCategory.EXPR_MOUTH_E,
        ReferenceAssetCategory.EXPR_MOUTH_I,
        ReferenceAssetCategory.EXPR_MOUTH_O,
        ReferenceAssetCategory.EXPR_MOUTH_U,
        ReferenceAssetCategory.EXPR_JAW_OPEN,
        ReferenceAssetCategory.EXPR_CHEEK_RAISE,
        ReferenceAssetCategory.EXPR_BROW_UP,
        ReferenceAssetCategory.EXPR_BROW_DOWN,
    }
)


class AssetUploadState(StrEnum):
    """MISSING nunca é persistido — é só o estado reportado pelo cálculo de completeness
    (seção 16) para um slot de ângulo/categoria que ainda não tem asset nenhum."""

    MISSING = "missing"
    UPLOADED = "uploaded"
    QA_PENDING = "qa_pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class QAStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NOT_CHECKED = "not_checked"
    REQUIRES_HUMAN = "requires_human"
    REQUIRES_MODEL = "requires_model"


class RejectionReason(StrEnum):
    IDENTITY_DRIFT = "identity_drift"
    ANGLE_WRONG = "angle_wrong"
    BLUR = "blur"
    LIGHTING = "lighting"
    HAIR_INCONSISTENT = "hair_inconsistent"
    BODY_INCONSISTENT = "body_inconsistent"
    HAND_INCONSISTENT = "hand_inconsistent"
    TEETH_INCONSISTENT = "teeth_inconsistent"
    BACKGROUND_INTERFERENCE = "background_interference"
    CLOTHING_INCONSISTENT = "clothing_inconsistent"
    OTHER = "other"


class GateDecisionAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_RECAPTURE = "request_recapture"


class QualityGateName(StrEnum):
    """Um gate por transição de status não-trivial (seção 3/4) — as duas transições que
    só "iniciam trabalho" (IDENTITY_LOCKED→MULTIVIEW_IN_PROGRESS,
    MULTIVIEW_APPROVED→MESH_IN_PROGRESS) não têm gate: nada para aprovar ainda, seguem
    pelo PATCH genérico de `dhf_avatars` como já funcionava antes desta missão."""

    IDENTITY = "identity"
    MULTIVIEW = "multiview"
    MESH = "mesh"
    RIG = "rig"
    MATERIALS = "materials"
    FACE = "face"
    VOICE = "voice"
    MOTION = "motion"
    MASTER = "master"
    PRODUCTION = "production"


class QualityGateStatus(StrEnum):
    NOT_TESTED = "not_tested"
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    REQUIRES_HUMAN = "requires_human"
    REQUIRES_MODEL = "requires_model"


# Checklist inicial de cada gate (seções 22-24) — todo item começa NOT_TESTED; nenhum
# check automático existe ainda para mesh/materials/face (dependem da RTX 4090 real).
GATE_CHECKLISTS: dict[QualityGateName, tuple[str, ...]] = {
    QualityGateName.MESH: (
        "silhouette",
        "facial_proportions",
        "eyes",
        "nose",
        "mouth",
        "jaw",
        "ears",
        "hairline",
        "neck",
        "shoulders",
        "body_proportions",
        "hands",
        "feet",
        "topology",
        "symmetry",
        "identity_similarity",
    ),
    QualityGateName.MATERIALS: (
        "skin_color",
        "subsurface",
        "pores",
        "roughness",
        "normal",
        "eyes",
        "cornea",
        "sclera",
        "tear_line",
        "teeth",
        "gums",
        "tongue",
        "hair",
        "clothing",
    ),
    QualityGateName.FACE: (
        "neutral_expression",
        "blink",
        "eyes",
        "gaze",
        "lip_sync",
        "mouth_interior",
        "smile",
        "jaw",
        "cheeks",
        "brows",
        "microexpressions",
        "asymmetry",
        "temporal_consistency",
    ),
}


class DerivedAssetType(StrEnum):
    RECONSTRUCTED_MESH = "reconstructed_mesh"
    RETOPOLOGY_MESH = "retopology_mesh"
    TEXTURE_ALBEDO = "texture_albedo"
    TEXTURE_NORMAL = "texture_normal"
    TEXTURE_ROUGHNESS = "texture_roughness"
    GROOM = "groom"
    METAHUMAN_ASSET = "metahuman_asset"
    RIG = "rig"
    FACIAL_RIG = "facial_rig"
    LOD = "lod"
    THUMBNAIL = "thumbnail"
    PREVIEW_RENDER = "preview_render"


class DerivedAssetStatus(StrEnum):
    NOT_GENERATED = "not_generated"
    QUEUED = "queued"
    GENERATING = "generating"
    GENERATED = "generated"
    FAILED = "failed"


class JobContractType(StrEnum):
    MULTIVIEW_RECONSTRUCTION = "multiview_reconstruction"
    MESH_REFINEMENT = "mesh_refinement"
    TEXTURE_GENERATION = "texture_generation"
    METAHUMAN_CONVERSION = "metahuman_conversion"
    FACIAL_RIG = "facial_rig"
    GROOM_BUILD = "groom_build"
    MATERIAL_BUILD = "material_build"
    QUALITY_RENDER = "quality_render"


class HardwareRequirement(StrEnum):
    CPU = "cpu"
    GPU_ANY = "gpu_any"
    RTX_CLASS = "rtx_class"
    RTX_4090 = "rtx_4090"
    AI_HEAVY = "ai_heavy"


class JobContractStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    BLOCKED = "blocked"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Gate -> status alvo (seção 4) — as únicas 10 transições que exigem evidência real; as
# duas transições "_IN_PROGRESS" não têm gate, seguem pelo PATCH genérico de dhf_avatars.
# Centralizado aqui (não em service.py nem repository.py) porque P1-6 exige que a MESMA
# constante seja usada tanto pela validação quanto pela transação atômica que escreve —
# duplicá-la arriscaria as duas divergirem silenciosamente.
GATE_TARGET_STATUS: dict[QualityGateName, AvatarStatus] = {
    QualityGateName.IDENTITY: AvatarStatus.IDENTITY_LOCKED,
    QualityGateName.MULTIVIEW: AvatarStatus.MULTIVIEW_APPROVED,
    QualityGateName.MESH: AvatarStatus.MESH_APPROVED,
    QualityGateName.RIG: AvatarStatus.RIGGED,
    QualityGateName.MATERIALS: AvatarStatus.MATERIALS_APPROVED,
    QualityGateName.FACE: AvatarStatus.FACE_APPROVED,
    QualityGateName.VOICE: AvatarStatus.VOICE_APPROVED,
    QualityGateName.MOTION: AvatarStatus.MOTION_APPROVED,
    QualityGateName.MASTER: AvatarStatus.MASTER_APPROVED,
    QualityGateName.PRODUCTION: AvatarStatus.PRODUCTION_READY,
}

# Ordem canônica do pipeline (StrEnum já é declarado nesta ordem — `list(QualityGateName)`
# bastaria, mas nomear explicitamente evita que uma reordenação futura do enum mude a
# semântica de "downstream" por acidente).
GATE_ORDER: tuple[QualityGateName, ...] = (
    QualityGateName.IDENTITY,
    QualityGateName.MULTIVIEW,
    QualityGateName.MESH,
    QualityGateName.RIG,
    QualityGateName.MATERIALS,
    QualityGateName.FACE,
    QualityGateName.VOICE,
    QualityGateName.MOTION,
    QualityGateName.MASTER,
    QualityGateName.PRODUCTION,
)


def downstream_gates_of(gate_name: QualityGateName) -> tuple[QualityGateName, ...]:
    """Gates que vêm DEPOIS de `gate_name` no pipeline (P1-6b — invalidação em cascata):
    se a evidência de `gate_name` deixa de ser válida, nenhum gate downstream pode
    continuar PASS, já que seu enforcement presumia `gate_name` satisfeito."""
    index = GATE_ORDER.index(gate_name)
    return GATE_ORDER[index + 1 :]


_AVATAR_STATUS_ORDER: list[AvatarStatus] = list(AvatarStatus)


def predecessor_status_of(gate_name: QualityGateName) -> AvatarStatus:
    """O status imediatamente ANTERIOR ao alvo de `gate_name` (P1-6b): para onde o avatar
    regride quando esse gate é invalidado — ex.: se MULTIVIEW cai, o avatar volta para
    MULTIVIEW_IN_PROGRESS (não para trás demais, não IDENTITY_LOCKED), já que essa
    transição '_IN_PROGRESS' continua estruturalmente válida (o predecessor dela,
    IDENTITY_LOCKED, nunca deixou de estar satisfeito)."""
    target = GATE_TARGET_STATUS[gate_name]
    return _AVATAR_STATUS_ORDER[_AVATAR_STATUS_ORDER.index(target) - 1]
