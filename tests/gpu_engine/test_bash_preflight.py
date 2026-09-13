"""Testes reais (via subprocess) dos scripts bash corrigidos após a revisão de PR#4:
infra/gpu/audio2face/verify-requirements.sh e infra/gpu/metahuman/preflight.sh, mais os
helpers de comparação de versão em infra/gpu/lib/common.sh.

Por que subprocess (e não mockar em Python): os 3 erros P1 corrigidos (matriz CUDA/
TensorRT do Audio2Face-3D SDK, modelagem NIM-only, blanket Windows-only do MetaHuman)
estavam todos NO BASH, não no services/gpu_engine (Python) — só rodar o script de
verdade prova que a lógica de range-check e o branching por modo funcionam. `nvcc` e o
pacote `tensorrt` são "dublados" via um binário fake no PATH e um pacote fake no
PYTHONPATH — não precisam de GPU real nem dos toolkits de verdade instalados.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMON_SH = REPO_ROOT / "infra/gpu/lib/common.sh"
AUDIO2FACE_SCRIPT = REPO_ROOT / "infra/gpu/audio2face/verify-requirements.sh"
METAHUMAN_SCRIPT = REPO_ROOT / "infra/gpu/metahuman/preflight.sh"


def _make_fake_nvcc(bin_dir: Path, version: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    nvcc = bin_dir / "nvcc"
    nvcc.write_text(
        f'#!/usr/bin/env bash\necho "Cuda compilation tools, release {version}, V{version}.41"\n'
    )
    nvcc.chmod(0o755)


def _make_fake_tensorrt(pylib_dir: Path, version: str) -> None:
    pkg_dir = pylib_dir / "tensorrt"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text(f'__version__ = "{version}"\n')


def _base_env(results_file: Path) -> dict[str, str]:
    env = dict(os.environ)
    # Hermético: nunca herdar AUDIO2FACE_MODE/NGC_API_KEY de um ambiente externo (ex.:
    # secret de CI) — cada teste decide explicitamente o que quer testar.
    env.pop("AUDIO2FACE_MODE", None)
    env.pop("NGC_API_KEY", None)
    env["GPU_ENGINE_RESULTS_FILE"] = str(results_file)
    return env


def _run_script(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _read_results(results_file: Path) -> dict[str, dict[str, str]]:
    if not results_file.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    for line in results_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        rows[row["name"]] = row
    return rows


class TestAudio2FaceLocalSdkVersionGates:
    """P1#1 — o teto do Audio2Face-3D SDK (CUDA <13.0, TensorRT <11.0) precisa ser
    aplicado de verdade, não só documentado em comentário."""

    def test_rejects_cuda_13_or_newer(self, tmp_path: Path) -> None:
        fake_bin = tmp_path / "fakebin"
        _make_fake_nvcc(fake_bin, "13.4")
        fake_pylib = tmp_path / "fakepylib"
        _make_fake_tensorrt(fake_pylib, "10.13.0")

        env = _base_env(tmp_path / "results.jsonl")
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        env["PYTHONPATH"] = str(fake_pylib)

        proc = _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["audio2face_local_sdk_cuda_range"]["status"] == "FAIL"
        assert "13.4" in results["audio2face_local_sdk_cuda_range"]["detail"]
        # o script só reporta (nunca aborta sozinho) — quem decide o que fazer com um
        # FAIL é audio2face/preflight.sh (AUDIO2FACE_READY_FOR_INSTALL).
        assert proc.returncode == 0

    def test_rejects_tensorrt_11_or_newer(self, tmp_path: Path) -> None:
        fake_bin = tmp_path / "fakebin"
        _make_fake_nvcc(fake_bin, "12.9")
        fake_pylib = tmp_path / "fakepylib"
        _make_fake_tensorrt(fake_pylib, "11.0.0")

        env = _base_env(tmp_path / "results.jsonl")
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        env["PYTHONPATH"] = str(fake_pylib)

        _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["audio2face_local_sdk_tensorrt_range"]["status"] == "FAIL"
        assert "11.0.0" in results["audio2face_local_sdk_tensorrt_range"]["detail"]

    def test_accepts_versions_inside_the_compatible_range(self, tmp_path: Path) -> None:
        fake_bin = tmp_path / "fakebin"
        _make_fake_nvcc(fake_bin, "12.9")
        fake_pylib = tmp_path / "fakepylib"
        _make_fake_tensorrt(fake_pylib, "10.13.0")

        env = _base_env(tmp_path / "results.jsonl")
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        env["PYTHONPATH"] = str(fake_pylib)

        _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["audio2face_local_sdk_cuda_range"]["status"] == "PASS"
        assert results["audio2face_local_sdk_tensorrt_range"]["status"] == "PASS"


class TestAudio2FaceModeScoping:
    """P1#2 — Audio2Face-3D não é NIM-only: local_sdk é o padrão e nunca deve exigir
    NGC_API_KEY/Docker; NIM continua existindo como modo separado e opcional."""

    def test_default_mode_is_local_sdk(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")

        _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["audio2face_mode"]["detail"].endswith("local_sdk")

    def test_local_sdk_does_not_require_ngc_api_key(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")
        # NGC_API_KEY deliberadamente ausente — local_sdk não pode travar por causa disso.

        proc = _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["audio2face_ngc_api_key"]["status"] != "FAIL"
        assert not any(row["status"] == "FAIL" for row in results.values())
        assert proc.returncode == 0

    def test_nim_mode_warns_without_ngc_api_key(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")
        env["AUDIO2FACE_MODE"] = "nim"

        _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["audio2face_nim_ngc_api_key"]["status"] == "WARN"

    def test_nim_mode_accepts_configured_ngc_api_key(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")
        env["AUDIO2FACE_MODE"] = "nim"
        env["NGC_API_KEY"] = "test-key-not-real"

        _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["audio2face_nim_ngc_api_key"]["status"] == "PASS"
        # nunca ecoar o valor da chave no detail (mesmo sendo uma chave falsa de teste).
        assert "test-key-not-real" not in results["audio2face_nim_ngc_api_key"]["detail"]

    def test_mode_env_var_overrides_versions_env_default(self, tmp_path: Path) -> None:
        """Regressão: versions.env chegou a sobrescrever incondicionalmente
        AUDIO2FACE_MODE vindo do ambiente (bug encontrado rodando o próprio script
        durante esta revisão) — sem o `${AUDIO2FACE_MODE:-local_sdk}` em versions.env,
        este teste falha porque o modo nim nunca é selecionado."""
        env = _base_env(tmp_path / "results.jsonl")
        env["AUDIO2FACE_MODE"] = "nim"

        _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["audio2face_mode"]["detail"].endswith("nim")
        assert "audio2face_nim_docker" in results

    def test_invalid_mode_fails_fast(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")
        env["AUDIO2FACE_MODE"] = "bogus"

        proc = _run_script(AUDIO2FACE_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert proc.returncode == 1
        assert results["audio2face_mode"]["status"] == "FAIL"


class TestMetaHumanLinuxSupport:
    """P1#3 — MetaHuman Animator não é Windows-only em bloco: facial é suportado no
    Linux, só body/markerless capture não é."""

    def test_facial_linux_is_supported(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")

        _run_script(METAHUMAN_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        detail = results["metahuman_animator_facial_linux"]["detail"].lower()
        assert results["metahuman_animator_facial_linux"]["status"] == "PASS"
        # a mensagem pode mencionar "Windows-only" só para NEGAR (ex.: "não é
        # Windows-only") — o que não pode acontecer é ela dizer que precisa de Windows.
        assert "requer windows" not in detail
        assert "precisa de windows" not in detail
        assert "facial" in detail

    def test_body_markerless_linux_is_unsupported_platform(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")

        _run_script(METAHUMAN_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        detail = results["metahuman_body_markerless_linux"]["detail"].lower()
        assert results["metahuman_body_markerless_linux"]["status"] == "SKIP"
        assert "unsupported_platform" in detail or "windows-only" in detail

    def test_never_generalizes_entire_animator_as_windows_only(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")

        _run_script(METAHUMAN_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        # Regressão: a versão anterior marcava um "metahuman_animator_linux" único como
        # SKIP/Windows-only para o Animator inteiro — esse nome não deve mais existir.
        assert "metahuman_animator_linux" not in results
        # Identity/Performance não confirmado != generalizado como Windows-only: fica
        # NOT_TESTED (honesto), nunca SKIP/FAIL carimbando tudo como incompatível.
        assert results["metahuman_identity_performance_linux"]["status"] == "NOT_TESTED"

    def test_creator_still_supported(self, tmp_path: Path) -> None:
        env = _base_env(tmp_path / "results.jsonl")

        proc = _run_script(METAHUMAN_SCRIPT, env)
        results = _read_results(tmp_path / "results.jsonl")

        assert results["metahuman_creator_linux"]["status"] == "PASS"
        assert proc.returncode == 0


def _bash_check(expr: str) -> bool:
    proc = subprocess.run(
        ["bash", "-c", f'source "{COMMON_SH}" && {expr}'],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return proc.returncode == 0


class TestVersionRangeHelpers:
    """Cobertura direta de version_ge/version_lt/version_in_range (lib/common.sh) nas
    fronteiras exatas exigidas pela correção: teto exclusivo em CUDA 13.0 e TensorRT
    11.0.0 do Audio2Face-3D SDK."""

    def test_cuda_13_0_is_rejected_by_audio2face_ceiling(self) -> None:
        assert not _bash_check('version_in_range "13.0" "12.8" "13.0"')

    def test_cuda_above_13_is_rejected(self) -> None:
        assert not _bash_check('version_in_range "13.4" "12.8" "13.0"')

    def test_cuda_12_9_is_accepted(self) -> None:
        assert _bash_check('version_in_range "12.9" "12.8" "13.0"')

    def test_tensorrt_11_0_0_is_rejected_by_audio2face_ceiling(self) -> None:
        assert not _bash_check('version_in_range "11.0.0" "10.13.0" "11.0.0"')

    def test_tensorrt_10_13_0_is_accepted(self) -> None:
        assert _bash_check('version_in_range "10.13.0" "10.13.0" "11.0.0"')

    def test_tensorrt_below_min_is_rejected(self) -> None:
        assert not _bash_check('version_in_range "10.12.9" "10.13.0" "11.0.0"')
