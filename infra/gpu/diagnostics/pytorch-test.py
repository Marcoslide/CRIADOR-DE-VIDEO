#!/usr/bin/env python3
"""pytorch-test.py — teste real de PyTorch+CUDA (seção 14 da missão): is_available(),
device name, VRAM total, compute capability, multiplicação de matriz real, tempo, peak
memory. NOT_TESTED se torch não estiver instalado; REQUIRES_GPU se torch estiver
instalado mas sem CUDA disponível — nunca finge um resultado.

Códigos de saída: 0 = PASS, 1 = FAIL, 2 = NOT_TESTED/REQUIRES_GPU.

Uso:
    python3 pytorch-test.py [--json] [--matrix-size 4096]
"""

from __future__ import annotations

import argparse
import json
import sys


def run(matrix_size: int) -> dict:
    try:
        import torch
    except ImportError:
        return {
            "status": "NOT_TESTED",
            "detail": "PyTorch não instalado — rode 08-python-ai.sh antes deste teste",
        }

    if not torch.cuda.is_available():
        return {
            "status": "REQUIRES_GPU",
            "detail": (
                f"torch {torch.__version__} instalado, mas torch.cuda.is_available() == False"
            ),
            "torch_version": torch.__version__,
        }

    device_name = torch.cuda.get_device_name(0)
    capability = torch.cuda.get_device_capability(0)
    vram_total_mb = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)

    torch.cuda.reset_peak_memory_stats(0)
    torch.cuda.synchronize()

    a = torch.randn(matrix_size, matrix_size, device="cuda")
    b = torch.randn(matrix_size, matrix_size, device="cuda")

    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    c = a @ b
    end.record()
    torch.cuda.synchronize()

    elapsed_ms = start.elapsed_time(end)
    peak_memory_mb = torch.cuda.max_memory_allocated(0) / (1024 * 1024)
    result_finite = bool(torch.isfinite(c).all().item())

    del a, b, c
    torch.cuda.empty_cache()

    return {
        "status": "PASS" if result_finite else "FAIL",
        "torch_version": torch.__version__,
        "device_name": device_name,
        "compute_capability": f"{capability[0]}.{capability[1]}",
        "vram_total_mb": round(vram_total_mb, 1),
        "matrix_size": matrix_size,
        "matmul_elapsed_ms": round(elapsed_ms, 3),
        "peak_memory_mb": round(peak_memory_mb, 1),
        "result_finite": result_finite,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--matrix-size", type=int, default=4096)
    args = parser.parse_args()

    result = run(args.matrix_size)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status = result["status"]
        if status == "PASS":
            print(
                f"[PASS] {result['device_name']} — torch {result['torch_version']} "
                f"(cc {result['compute_capability']})"
            )
            print(
                f"       VRAM total: {result['vram_total_mb']}MB, "
                f"matmul {result['matrix_size']}x{result['matrix_size']}: "
                f"{result['matmul_elapsed_ms']}ms, peak memory: {result['peak_memory_mb']}MB"
            )
        else:
            print(f"[{status}] {result['detail']}")

    return {"PASS": 0, "FAIL": 1}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
