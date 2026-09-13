#!/usr/bin/env python3
"""benchmark_nvenc.py — matriz completa de encode NVENC pedida na seção 17 da missão:
1080p e 4K × H.264/HEVC/AV1. Para cada combinação, mede FPS de encode, tempo total,
bitrate resultante, tamanho do arquivo, e amostra utilização de GPU/encoder durante o
encode (thread de amostragem via nvidia-smi rodando em paralelo ao ffmpeg — não é uma
média inventada, é a média das amostras reais coletadas durante a execução).

Uso:
    python3 benchmark_nvenc.py [--json] [--duration 5]
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RESOLUTIONS = {"1080p": "1920x1080", "4k": "3840x2160"}
CODECS = ["h264_nvenc", "hevc_nvenc", "av1_nvenc"]


class _GpuSampler:
    """Amostra utilization.gpu/utilization.encoder via nvidia-smi a cada 200ms enquanto
    o encode roda, numa thread separada — não bloqueia o ffmpeg sendo medido."""

    def __init__(self) -> None:
        self._samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                out = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=utilization.gpu,utilization.encoder",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                ).stdout.strip()
                gpu_str, enc_str = (p.strip() for p in out.split(","))
                self._samples.append((float(gpu_str), float(enc_str)))
            except Exception:  # noqa: BLE001 — amostragem best-effort, nunca derruba o benchmark
                pass
            self._stop.wait(0.2)

    def __enter__(self) -> _GpuSampler:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def averages(self) -> tuple[float | None, float | None]:
        if not self._samples:
            return None, None
        gpu_avg = statistics.mean(s[0] for s in self._samples)
        enc_avg = statistics.mean(s[1] for s in self._samples)
        return round(gpu_avg, 1), round(enc_avg, 1)


def _has_gpu() -> bool:
    return (
        shutil.which("nvidia-smi") is not None
        and subprocess.run(["nvidia-smi"], capture_output=True, timeout=5).returncode == 0
    )


def _available_encoders() -> set[str]:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    ).stdout
    return {codec for codec in CODECS if codec in out}


def _bench_one(resolution_name: str, size: str, codec: str, duration: int, tmpdir: Path) -> dict:
    out_file = tmpdir / f"{resolution_name}_{codec}.mp4"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size={size}:rate=30",
        "-c:v",
        codec,
        "-pix_fmt",
        "yuv420p",
        str(out_file),
    ]

    with _GpuSampler() as sampler:
        started = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        elapsed_s = time.perf_counter() - started

    if proc.returncode != 0:
        return {"status": "FAIL", "detail": proc.stderr[-500:]}

    frames_encoded = duration * 30
    fps = frames_encoded / elapsed_s if elapsed_s > 0 else None
    file_size_bytes = out_file.stat().st_size if out_file.exists() else 0
    bitrate_mbps = (file_size_bytes * 8 / elapsed_s / 1_000_000) if elapsed_s > 0 else None
    gpu_util_avg, enc_util_avg = sampler.averages()
    out_file.unlink(missing_ok=True)

    return {
        "status": "PASS",
        "elapsed_s": round(elapsed_s, 2),
        "fps": round(fps, 1) if fps else None,
        "realtime_factor": round(fps / 30, 2) if fps else None,
        "file_size_bytes": file_size_bytes,
        "bitrate_mbps": round(bitrate_mbps, 2) if bitrate_mbps else None,
        "gpu_utilization_avg_pct": gpu_util_avg,
        "encoder_utilization_avg_pct": enc_util_avg,
    }


def run(duration: int) -> dict:
    if shutil.which("ffmpeg") is None:
        return {"status": "NOT_TESTED", "detail": "ffmpeg não instalado"}
    if not _has_gpu():
        return {"status": "REQUIRES_GPU", "detail": "sem GPU NVIDIA neste ambiente"}

    available = _available_encoders()
    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for res_name, size in RESOLUTIONS.items():
            for codec in CODECS:
                key = f"{res_name}_{codec}"
                if codec not in available:
                    results[key] = {
                        "status": "SKIP",
                        "detail": "encoder não presente neste build do ffmpeg",
                    }
                    continue
                results[key] = _bench_one(res_name, size, codec, duration, tmpdir)

    return {"status": "PASS", "duration_s_per_test": duration, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--duration", type=int, default=5)
    args = parser.parse_args()

    result = run(args.duration)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["status"] != "PASS":
            print(f"[{result['status']}] {result.get('detail')}")
        else:
            for key, value in result["results"].items():
                print(f"{key}: {value}")

    return {"PASS": 0, "FAIL": 1}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
