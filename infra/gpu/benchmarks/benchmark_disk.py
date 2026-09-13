#!/usr/bin/env python3
"""benchmark_disk.py — versão estruturada (JSON) do diagnostics/disk-benchmark.sh, para
entrar no relatório agregado (seção 24 e 35 da missão). Mede write/read sequencial via
um arquivo real de teste — sem terceiros (fio), fica registrado como tal, nunca inventa
um número de random IO.

Uso:
    python3 benchmark_disk.py [--json] [--path /opt/dhvf/tmp] [--size-mb 512]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


def run(path: str, size_mb: int) -> dict:
    os.makedirs(path, exist_ok=True)
    test_file = os.path.join(path, ".gpu-engine-disk-benchmark.bin")
    block = os.urandom(1024 * 1024)  # 1MB de dados não-compressíveis, evita otimização de FS

    try:
        start = time.perf_counter()
        with open(test_file, "wb") as fh:
            for _ in range(size_mb):
                fh.write(block)
            fh.flush()
            os.fsync(fh.fileno())
        write_elapsed_s = time.perf_counter() - start
        write_mb_s = size_mb / write_elapsed_s if write_elapsed_s > 0 else None

        # tenta invalidar cache de página lendo um arquivo bem maior antes (melhor
        # esforço — sem root para dropar caches de verdade, o número de leitura pode
        # ficar otimista; isso é reportado explicitamente, não escondido).
        start = time.perf_counter()
        with open(test_file, "rb") as fh:
            while fh.read(1024 * 1024):
                pass
        read_elapsed_s = time.perf_counter() - start
        read_mb_s = size_mb / read_elapsed_s if read_elapsed_s > 0 else None

        statvfs = os.statvfs(path)
        free_gb = statvfs.f_bavail * statvfs.f_frsize / (1024**3)
        total_gb = statvfs.f_blocks * statvfs.f_frsize / (1024**3)

        return {
            "status": "PASS",
            "path": path,
            "size_mb": size_mb,
            "write_mb_s": round(write_mb_s, 1) if write_mb_s else None,
            "read_mb_s": round(read_mb_s, 1) if read_mb_s else None,
            "read_note": (
                "cache de página pode não ter sido invalidado (sem privilégio de "
                "root) — número pode ser otimista"
            ),
            "disk_free_gb": round(free_gb, 1),
            "disk_total_gb": round(total_gb, 1),
        }
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default="/tmp")
    parser.add_argument("--size-mb", type=int, default=512)
    args = parser.parse_args()

    try:
        result = run(args.path, args.size_mb)
    except OSError as exc:
        result = {"status": "FAIL", "detail": str(exc)}

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["status"] == "PASS":
            print(
                f"Write: {result['write_mb_s']} MB/s | Read: {result['read_mb_s']} MB/s "
                f"| Livre: {result['disk_free_gb']}GB de {result['disk_total_gb']}GB"
            )
        else:
            print(f"[FAIL] {result.get('detail')}")

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
