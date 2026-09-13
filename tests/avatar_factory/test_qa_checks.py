"""Testes unitários do QA Engine determinístico (seção 13) — sem DB, sem rede, sem
Storage: só a lógica pura de `dhf_avatar_factory.qa_checks` sobre bytes de imagem reais
gerados em memória via Pillow."""

from __future__ import annotations

import random
from io import BytesIO

from dhf_avatar_factory.enums import QAStatus
from dhf_avatar_factory.qa_checks import compute_checksum, run_deterministic_checks
from PIL import Image


def _png_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _noisy_png_bytes(size: tuple[int, int], *, seed: int = 42) -> bytes:
    """Ruído por pixel (não um bloco de cor sólida): textura genuína o bastante para dar
    variância de bordas alta (heurística de blur) sem saturar nenhum pixel em 0/255
    (evita disparar o check de exposição junto)."""
    rng = random.Random(seed)
    image = Image.new("RGB", size)
    pixels = image.load()
    for x in range(size[0]):
        for y in range(size[1]):
            value = rng.randint(20, 235)
            pixels[x, y] = (value, value, value)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_valid_sharp_image_passes_all_checks() -> None:
    data = _noisy_png_bytes((640, 640))

    result = run_deterministic_checks(data)

    assert result.status == QAStatus.PASS
    assert result.width == 640
    assert result.height == 640
    assert result.checksum == compute_checksum(data)
    assert result.checks["file_validity"]["status"] == QAStatus.PASS
    assert result.checks["duplicate_file"]["status"] == QAStatus.PASS
    assert result.checks["blur_heuristic"]["status"] == QAStatus.PASS
    assert result.checks["face_presence"]["status"] == QAStatus.NOT_CHECKED


def test_corrupt_bytes_fail_file_validity() -> None:
    result = run_deterministic_checks(b"isto nao e uma imagem de verdade")

    assert result.status == QAStatus.FAIL
    assert result.checks["file_validity"]["status"] == QAStatus.FAIL
    assert result.width is None


def test_duplicate_checksum_fails_before_decoding() -> None:
    data = _noisy_png_bytes((640, 640))
    checksum = compute_checksum(data)

    result = run_deterministic_checks(data, existing_checksums=frozenset({checksum}))

    assert result.status == QAStatus.FAIL
    assert result.checks["duplicate_file"]["status"] == QAStatus.FAIL
    assert "file_validity" not in result.checks  # nem chega a tentar decodificar


def test_small_image_warns_minimum_dimensions() -> None:
    data = _noisy_png_bytes((64, 64))

    result = run_deterministic_checks(data)

    assert result.status == QAStatus.WARN
    assert result.checks["minimum_dimensions"]["status"] == QAStatus.WARN


def test_flat_color_image_warns_blur_heuristic() -> None:
    """Uma imagem sem nenhuma borda (cor sólida) é o caso mais óbvio de 'desfocada' para
    a heurística de variância de bordas — nunca reprova (FAIL), só WARN (é heurística)."""
    data = _png_bytes((640, 640), color=(128, 128, 128))

    result = run_deterministic_checks(data)

    assert result.checks["blur_heuristic"]["status"] == QAStatus.WARN
    assert result.status == QAStatus.WARN


def test_overexposed_image_warns_exposure_clipping() -> None:
    data = _png_bytes((640, 640), color=(255, 255, 255))

    result = run_deterministic_checks(data)

    assert result.checks["exposure_clipping"]["status"] == QAStatus.WARN


def test_checksum_is_stable_sha256() -> None:
    data = "conteúdo determinístico".encode()
    assert compute_checksum(data) == compute_checksum(data)
    assert len(compute_checksum(data)) == 64
