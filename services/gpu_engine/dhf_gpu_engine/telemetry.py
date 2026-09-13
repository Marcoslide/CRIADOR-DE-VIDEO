"""Telemetria estruturada (seção 21 da missão): GPU%, VRAM, temperatura, power, CPU,
RAM, SSD, NVENC, decoder, lista de processos — tudo num único JSON. CPU/RAM/SSD vêm do
próprio sistema (não dependem de GPU); o resto vem de `capabilities.detect_capabilities()`
e do VramManager quando fornecido.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from typing import Any

from dhf_gpu_engine.capabilities import detect_capabilities
from dhf_gpu_engine.schemas import TelemetrySnapshot
from dhf_gpu_engine.vram_manager import VramManager


def _cpu_ram_disk_snapshot() -> dict[str, Any]:
    load1, load5, load15 = os.getloadavg()
    ram_total_mb = ram_free_mb = None
    try:
        with open("/proc/meminfo") as fh:
            meminfo = {line.split(":")[0]: line.split(":")[1].strip() for line in fh if ":" in line}
        ram_total_mb = int(meminfo["MemTotal"].split()[0]) / 1024
        ram_free_mb = int(meminfo["MemAvailable"].split()[0]) / 1024
    except (OSError, KeyError, ValueError, IndexError):
        pass

    disk = shutil.disk_usage("/")

    return {
        "cpu_load_1m": load1,
        "cpu_load_5m": load5,
        "cpu_load_15m": load15,
        "cpu_count": os.cpu_count(),
        "ram_total_mb": ram_total_mb,
        "ram_free_mb": ram_free_mb,
        "disk_total_gb": disk.total / (1024**3),
        "disk_free_gb": disk.free / (1024**3),
    }


def _gpu_processes() -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []

    processes = []
    for line in proc.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            processes.append(
                {"pid": parts[0], "process_name": parts[1], "used_memory_mb": parts[2]}
            )
    return processes


def collect_telemetry(vram_manager: VramManager | None = None) -> TelemetrySnapshot:
    capabilities = detect_capabilities()
    system = _cpu_ram_disk_snapshot()
    processes = _gpu_processes()

    return TelemetrySnapshot(
        capabilities=capabilities,
        vram=vram_manager.status() if vram_manager else None,
        loaded_models=vram_manager.loaded_models() if vram_manager else [],
        processes=[{"system": system}, *processes],
        captured_at=datetime.now(UTC),
    )
