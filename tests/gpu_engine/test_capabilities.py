"""Testes de dhf_gpu_engine.capabilities — sem mocks para o caminho real "sem GPU" (é
literalmente verdade neste ambiente de CI/dev, e é o caminho mais importante de provar:
nunca retornar um valor de GPU inventado quando ela não existe). Um teste com
monkeypatch prova que o parser funciona corretamente também no caminho "com GPU", sem
precisar de hardware real para isso.
"""

from __future__ import annotations

import subprocess

import pytest
from dhf_gpu_engine.capabilities import detect_capabilities


def test_detect_capabilities_without_nvidia_smi_reports_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    caps = detect_capabilities()

    assert caps.status.value == "not_configured"
    assert caps.gpu_model is None
    assert caps.vram_total_mb is None
    assert caps.driver_version is None


def test_detect_capabilities_parses_real_nvidia_smi_csv_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simula a saída real de `nvidia-smi --query-gpu=... --format=csv,noheader,nounits`
    para uma RTX 4090 — prova que o parser funciona sem precisar de hardware real."""
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda name: f"/usr/bin/{name}")

    def fake_run(cmd, capture_output=True, text=True, timeout=5.0):  # noqa: ARG001
        if "--query-gpu=name,driver_version" in " ".join(cmd):
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=(
                    "NVIDIA GeForce RTX 4090, 580.65.06, 24564, 23800, 45, "
                    "120.5, 450.0, 12, 3, 8.9\n"
                ),
                stderr="",
            )
        if "utilization.encoder" in " ".join(cmd):
            return subprocess.CompletedProcess(cmd, 0, stdout="0\n", stderr="")
        if "utilization.decoder" in " ".join(cmd):
            return subprocess.CompletedProcess(cmd, 0, stdout="0\n", stderr="")
        if cmd[0] == "nvcc":
            return subprocess.CompletedProcess(
                cmd, 0, stdout="Cuda compilation tools, release 13.4, V13.4.106\n", stderr=""
            )
        if cmd[0] == "python3":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ModuleNotFoundError")
        if cmd[0] == "ffmpeg":
            return subprocess.CompletedProcess(
                cmd, 0, stdout=" V..... h264_nvenc  ...\n V..... hevc_nvenc ...\n", stderr=""
            )
        if cmd[0] == "vulkaninfo":
            return subprocess.CompletedProcess(
                cmd, 0, stdout="deviceName = NVIDIA GeForce RTX 4090\n", stderr=""
            )
        raise AssertionError(f"comando inesperado no teste: {cmd}")

    monkeypatch.setattr("dhf_gpu_engine.capabilities._run", fake_run)

    caps = detect_capabilities()

    assert caps.status.value == "connected"
    assert caps.gpu_model == "NVIDIA GeForce RTX 4090"
    assert caps.driver_version == "580.65.06"
    assert caps.vram_total_mb == 24564.0
    assert caps.vram_free_mb == 23800.0
    assert caps.temperature_c == 45.0
    assert caps.cuda_capability == "8.9"
    assert caps.cuda_version == "13.4"
    assert caps.has_nvenc is True
    assert "h264_nvenc" in caps.nvenc_codecs
    assert "hevc_nvenc" in caps.nvenc_codecs
    assert "av1_nvenc" not in caps.nvenc_codecs
    assert caps.graphics_capable is True
    assert caps.graphics_capable_source == "vulkaninfo_live_probe"
    # RTX está na tabela estática de RT cores conhecidos — marcado com a fonte certa,
    # nunca com a mesma confiança de uma checagem ao vivo.
    assert caps.raytracing_capable is True
    assert caps.raytracing_capable_source == "known_hardware_table"


def test_detect_capabilities_reports_error_when_nvidia_smi_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda name: f"/usr/bin/{name}")

    def fake_run(cmd, capture_output=True, text=True, timeout=5.0):  # noqa: ARG001
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Failed to initialize NVML")

    monkeypatch.setattr("dhf_gpu_engine.capabilities._run", fake_run)

    caps = detect_capabilities()

    assert caps.status.value == "error"
    assert "NVML" in (caps.detail or "")
