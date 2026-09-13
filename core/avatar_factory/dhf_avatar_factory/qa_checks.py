"""QA Engine determinístico (seção 13) — nenhuma classificação de identidade acontece
aqui, só checks objetivos e reproduzíveis sobre o arquivo em si (resolução, validade,
duplicata exata, heurística de blur/exposição). `face_presence` fica explicitamente
`NOT_CHECKED`: exigiria uma biblioteca de detecção facial que este V1 não instala (a
própria seção 13 hedge isso — "apenas se biblioteca estável e CPU-friendly"). Nunca
classifica identidade automaticamente como PASS sem um modelo real."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, ImageFilter, ImageStat

from dhf_avatar_factory.enums import QAStatus

MIN_DIMENSION_PX = 512
# Calibrado empiricamente (ver tests/avatar_factory/test_qa_checks.py): uma imagem lisa
# de cor sólida fica na casa de 100-400 (artefato do próprio filtro nas bordas do
# frame); uma foto real ou uma imagem com textura genuína fica em milhares. 1000 dá
# margem folgada dos dois lados sem depender de um valor exato — é heurística, não
# medição definitiva (seção 13: "se tecnicamente confiável").
BLUR_VARIANCE_WARN_THRESHOLD = 1000.0
CLIPPING_WARN_RATIO = 0.05  # 5% dos pixels saturados em preto ou branco puro


@dataclass
class QACheckResult:
    status: QAStatus
    checks: dict[str, dict[str, str]] = field(default_factory=dict)
    width: int | None = None
    height: int | None = None
    checksum: str | None = None


def compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _aggregate(checks: dict[str, dict[str, str]]) -> QAStatus:
    statuses = {entry["status"] for entry in checks.values()}
    if QAStatus.FAIL in statuses:
        return QAStatus.FAIL
    if QAStatus.WARN in statuses:
        return QAStatus.WARN
    return QAStatus.PASS


def run_deterministic_checks(
    data: bytes, *, existing_checksums: frozenset[str] = frozenset()
) -> QACheckResult:
    """Roda todos os checks determinísticos sobre os bytes crus de uma imagem já
    recebida (o upload em si e a persistência no Storage são responsabilidade do
    service, não deste módulo — isto é função pura, fácil de testar sem rede/DB)."""
    checksum = compute_checksum(data)
    checks: dict[str, dict[str, str]] = {}

    if checksum in existing_checksums:
        checks["duplicate_file"] = {
            "status": QAStatus.FAIL,
            "detail": "checksum idêntico a um asset já existente para este avatar",
        }
        return QACheckResult(status=QAStatus.FAIL, checks=checks, checksum=checksum)
    checks["duplicate_file"] = {"status": QAStatus.PASS, "detail": "checksum único"}

    try:
        probe = Image.open(BytesIO(data))
        probe.verify()
        image = Image.open(BytesIO(data))  # verify() invalida o objeto — reabre para ler pixels
    except Exception as exc:
        checks["file_validity"] = {
            "status": QAStatus.FAIL,
            "detail": f"arquivo de imagem inválido ou corrompido: {exc}",
        }
        return QACheckResult(status=QAStatus.FAIL, checks=checks, checksum=checksum)
    checks["file_validity"] = {
        "status": QAStatus.PASS,
        "detail": f"formato {image.format} decodificado com sucesso",
    }

    width, height = image.size
    checks["aspect_ratio"] = {
        "status": QAStatus.PASS,
        "detail": f"{width}x{height} (razão {width / height:.3f})",
    }

    if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
        checks["minimum_dimensions"] = {
            "status": QAStatus.WARN,
            "detail": f"{width}x{height} abaixo do mínimo recomendado ({MIN_DIMENSION_PX}px)",
        }
    else:
        checks["minimum_dimensions"] = {"status": QAStatus.PASS, "detail": f"{width}x{height}"}

    grayscale = image.convert("L")
    try:
        edges = grayscale.filter(ImageFilter.FIND_EDGES)
        variance = ImageStat.Stat(edges).var[0]
        if variance < BLUR_VARIANCE_WARN_THRESHOLD:
            checks["blur_heuristic"] = {
                "status": QAStatus.WARN,
                "detail": (
                    f"variância de bordas {variance:.2f} abaixo de "
                    f"{BLUR_VARIANCE_WARN_THRESHOLD} — possivelmente desfocada "
                    "(heurística, não definitivo)"
                ),
            }
        else:
            checks["blur_heuristic"] = {
                "status": QAStatus.PASS,
                "detail": f"variância de bordas {variance:.2f}",
            }
    except Exception as exc:
        checks["blur_heuristic"] = {
            "status": QAStatus.NOT_CHECKED,
            "detail": f"heurística indisponível: {exc}",
        }

    histogram = grayscale.histogram()
    total_pixels = width * height
    clipped = histogram[0] + histogram[-1]
    clip_ratio = (clipped / total_pixels) if total_pixels else 0.0
    if clip_ratio > CLIPPING_WARN_RATIO:
        checks["exposure_clipping"] = {
            "status": QAStatus.WARN,
            "detail": f"{clip_ratio:.1%} dos pixels saturados em preto/branco puro",
        }
    else:
        checks["exposure_clipping"] = {
            "status": QAStatus.PASS,
            "detail": f"{clip_ratio:.1%} saturado",
        }

    checks["face_presence"] = {
        "status": QAStatus.NOT_CHECKED,
        "detail": (
            "detecção facial não implementada nesta versão — seção 13 permite pular "
            "quando não há biblioteca CPU-friendly estável instalada"
        ),
    }

    return QACheckResult(
        status=_aggregate(checks), checks=checks, width=width, height=height, checksum=checksum
    )
