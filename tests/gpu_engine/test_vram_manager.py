"""Testes de dhf_gpu_engine.vram_manager — lógica pura, não precisa de GPU real."""

from __future__ import annotations

import pytest
from dhf_gpu_engine.schemas import CheckStatus, ModelState
from dhf_gpu_engine.vram_manager import VramCriticalError, VramManager


def test_allocate_and_status_tracks_consumer() -> None:
    manager = VramManager(total_mb=24576, warning_pct=80, critical_pct=92)
    manager.allocate("audio2face", 4096)

    status = manager.status()
    assert status.allocated_mb == 4096
    assert status.by_consumer == {"audio2face": 4096}
    assert status.status == CheckStatus.PASS


def test_status_warns_above_warning_threshold() -> None:
    manager = VramManager(total_mb=10000, warning_pct=50, critical_pct=90)
    manager.allocate("model_a", 6000)

    assert manager.status().status == CheckStatus.WARN


def test_status_fails_above_critical_threshold_when_forced() -> None:
    manager = VramManager(total_mb=10000, warning_pct=50, critical_pct=90)
    manager.allocate("model_a", 9500, force=True)

    assert manager.status().status == CheckStatus.FAIL


def test_allocate_refuses_beyond_critical_without_force() -> None:
    manager = VramManager(total_mb=10000, warning_pct=50, critical_pct=90)

    with pytest.raises(VramCriticalError) as exc_info:
        manager.allocate("model_a", 9500)

    assert exc_info.value.requested_mb == 9500
    # nada foi alocado — a recusa é atômica, não parcial
    assert manager.allocated_mb == 0


def test_allocate_with_force_bypasses_critical_check() -> None:
    manager = VramManager(total_mb=10000, warning_pct=50, critical_pct=90)
    manager.allocate("model_a", 9500, force=True)

    assert manager.allocated_mb == 9500


def test_release_frees_vram() -> None:
    manager = VramManager(total_mb=10000)
    manager.allocate("model_a", 2000)
    manager.release("model_a")

    assert manager.allocated_mb == 0
    assert manager.status().by_consumer == {}


def test_mark_warm_removes_from_hot_allocation() -> None:
    manager = VramManager(total_mb=10000)
    manager.allocate("model_a", 2000)
    manager.mark_warm("model_a")

    assert manager.allocated_mb == 0  # WARM não conta como VRAM alocada
    models = manager.loaded_models()
    assert models[0].state == ModelState.WARM


def test_peak_mb_tracks_maximum_even_after_release() -> None:
    manager = VramManager(total_mb=10000)
    manager.allocate("model_a", 5000)
    manager.release("model_a")
    manager.allocate("model_b", 1000)

    assert manager.status().peak_mb == 5000


def test_total_mb_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positivo"):
        VramManager(total_mb=0)
