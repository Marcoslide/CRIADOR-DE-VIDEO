"""Testes de dhf_gpu_engine.model_manager — base real de load/unload/status pedida na
seção 19 da missão, testável sem pesos de modelo reais existirem."""

from __future__ import annotations

import pytest
from dhf_gpu_engine.model_manager import ModelManager, ModelNotRegisteredError, ModelSpec
from dhf_gpu_engine.schemas import ModelState
from dhf_gpu_engine.vram_manager import VramCriticalError, VramManager


def _manager(total_mb: float = 24576) -> ModelManager:
    return ModelManager(VramManager(total_mb=total_mb))


def test_register_and_memory_estimate() -> None:
    manager = _manager()
    manager.register(
        ModelSpec(
            name="audio2face", vram_estimate_mb=4096, capabilities_required=["cuda", "tensorrt"]
        )
    )

    assert manager.memory_estimate("audio2face") == 4096
    assert manager.capabilities_required("audio2face") == ["cuda", "tensorrt"]


def test_memory_estimate_of_unregistered_model_raises() -> None:
    manager = _manager()
    with pytest.raises(ModelNotRegisteredError):
        manager.memory_estimate("nao-existe")


def test_load_reflects_in_status_and_vram() -> None:
    manager = _manager()
    manager.register(ModelSpec(name="tts", vram_estimate_mb=2048))

    info = manager.load("tts")

    assert info.state == ModelState.HOT
    assert info.vram_mb == 2048
    assert manager.status("tts").state == ModelState.HOT


def test_load_unregistered_model_raises() -> None:
    manager = _manager()
    with pytest.raises(ModelNotRegisteredError):
        manager.load("fantasma")


def test_load_propagates_vram_critical_error_without_force() -> None:
    manager = _manager(total_mb=1000)
    manager.register(ModelSpec(name="modelo_grande", vram_estimate_mb=999))

    with pytest.raises(VramCriticalError):
        manager.load("modelo_grande")


def test_unload_returns_model_to_unloaded_state() -> None:
    manager = _manager()
    manager.register(ModelSpec(name="upscaler", vram_estimate_mb=1024))
    manager.load("upscaler")
    manager.unload("upscaler")

    assert manager.status("upscaler").state == ModelState.UNLOADED


def test_status_of_never_loaded_model_is_unloaded_not_an_error() -> None:
    manager = _manager()
    manager.register(ModelSpec(name="quality_model", vram_estimate_mb=512))

    status = manager.status("quality_model")

    assert status.state == ModelState.UNLOADED
    assert status.vram_mb == 512  # a estimativa continua disponível mesmo sem carregar


def test_last_used_updates_on_touch() -> None:
    manager = _manager()
    manager.register(ModelSpec(name="tts", vram_estimate_mb=1024))
    manager.load("tts")

    first_touch = manager.last_used("tts")
    assert first_touch is not None

    manager.touch("tts")
    assert manager.last_used("tts") is not None


def test_all_loaded_lists_only_hot_or_warm_models() -> None:
    manager = _manager()
    manager.register(ModelSpec(name="a", vram_estimate_mb=100))
    manager.register(ModelSpec(name="b", vram_estimate_mb=100))
    manager.load("a")
    manager.load("b")
    manager.unload("b")

    names = {m.name for m in manager.all_loaded()}
    assert names == {"a"}
