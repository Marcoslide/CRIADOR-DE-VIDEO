#!/usr/bin/env python3
"""benchmark_vram.py — mede o uso real de VRAM ao alocar buffers crescentes até um
limite configurável, registrando allocated/reserved/peak em cada passo (seção 18 da
missão — VRAM Manager). Não é uma simulação: aloca tensores CUDA de verdade via PyTorch
e lê os contadores reais do driver.

Uso:
    python3 benchmark_vram.py [--json] [--max-steps 8] [--step-mb 512]
"""

from __future__ import annotations

import argparse
import json
import sys


def run(max_steps: int, step_mb: int) -> dict:
    try:
        import torch
    except ImportError:
        return {"status": "NOT_TESTED", "detail": "PyTorch não instalado"}
    if not torch.cuda.is_available():
        return {"status": "REQUIRES_GPU", "detail": "torch.cuda.is_available() == False"}

    torch.cuda.reset_peak_memory_stats(0)
    total_vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)

    buffers = []
    steps = []
    elements_per_step = int(step_mb * 1024 * 1024 / 4)  # float32 = 4 bytes

    for step in range(1, max_steps + 1):
        try:
            buffers.append(torch.empty(elements_per_step, device="cuda"))
        except torch.cuda.OutOfMemoryError:
            steps.append(
                {"step": step, "status": "OOM", "detail": f"OOM ao tentar alocar mais {step_mb}MB"}
            )
            break

        allocated_mb = torch.cuda.memory_allocated(0) / (1024 * 1024)
        reserved_mb = torch.cuda.memory_reserved(0) / (1024 * 1024)
        peak_mb = torch.cuda.max_memory_allocated(0) / (1024 * 1024)
        steps.append(
            {
                "step": step,
                "allocated_mb": round(allocated_mb, 1),
                "reserved_mb": round(reserved_mb, 1),
                "peak_mb": round(peak_mb, 1),
                "pct_of_total": round(allocated_mb / total_vram_mb * 100, 1),
            }
        )

    del buffers
    torch.cuda.empty_cache()

    return {
        "status": "PASS",
        "total_vram_mb": round(total_vram_mb, 1),
        "step_mb": step_mb,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--step-mb", type=int, default=512)
    args = parser.parse_args()

    result = run(args.max_steps, args.step_mb)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status = result["status"]
        if status == "PASS":
            print(f"VRAM total: {result['total_vram_mb']}MB")
            for step in result["steps"]:
                print(f"  {step}")
        else:
            print(f"[{status}] {result.get('detail')}")

    return {"PASS": 0}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
