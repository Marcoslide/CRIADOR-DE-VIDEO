#!/usr/bin/env python3
"""benchmark_gpu.py — CUDA/TensorRT/PyTorch em conjunto (seção G / "CUDA" e "TensorRT" da
missão): roda os diagnostics de cuda-test.py e tensorrt-test.py e um matmul PyTorch em
múltiplos tamanhos, agregando tudo num único JSON. Serve de baseline antes de qualquer
otimização futura — não compara contra um número absoluto "aprovado", já que isso
dependeria de hardware que não existe neste ambiente de desenvolvimento.

Uso:
    python3 benchmark_gpu.py [--json] [--matrix-sizes 1024,2048,4096,8192]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DIAGNOSTICS_DIR = Path(__file__).resolve().parent.parent / "diagnostics"


def _run_diagnostic(script: str) -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, str(DIAGNOSTICS_DIR / script), "--json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return {"status": "NOT_TESTED", "detail": f"{script} não encontrado"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "status": "FAIL",
            "detail": f"{script} não retornou JSON válido: {proc.stdout!r} {proc.stderr!r}",
        }


def _matmul_benchmark(sizes: list[int]) -> dict:
    try:
        import torch
    except ImportError:
        return {"status": "NOT_TESTED", "detail": "PyTorch não instalado"}
    if not torch.cuda.is_available():
        return {"status": "REQUIRES_GPU", "detail": "torch.cuda.is_available() == False"}

    results = []
    for size in sizes:
        a = torch.randn(size, size, device="cuda")
        b = torch.randn(size, size, device="cuda")
        torch.cuda.synchronize()
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        _ = a @ b
        end.record()
        torch.cuda.synchronize()
        elapsed_ms = start.elapsed_time(end)
        gflops = (2 * size**3) / (elapsed_ms / 1000) / 1e9 if elapsed_ms > 0 else None
        results.append(
            {
                "matrix_size": size,
                "elapsed_ms": round(elapsed_ms, 3),
                "gflops": round(gflops, 1) if gflops else None,
            }
        )
        del a, b
        torch.cuda.empty_cache()

    return {"status": "PASS", "runs": results}


def _aggregate_status(sub_results: dict[str, dict]) -> str:
    statuses = {v.get("status") for v in sub_results.values()}
    if "FAIL" in statuses:
        return "FAIL"
    if statuses <= {"PASS"}:
        return "PASS"
    if "REQUIRES_GPU" in statuses:
        return "REQUIRES_GPU"
    return "NOT_TESTED"


def run(sizes: list[int]) -> dict:
    # Campo "status" no nível raiz — mesmo contrato dos outros benchmarks (disk/vram/
    # nvenc) — para quem consome só o JSON (ex.: GpuOrchestrator.run_benchmark) não
    # precisar conhecer a estrutura interna de cada benchmark para saber se passou.
    sub_results = {
        "cuda_runtime": _run_diagnostic("cuda-test.py"),
        "tensorrt": _run_diagnostic("tensorrt-test.py"),
        "pytorch_matmul": _matmul_benchmark(sizes),
    }
    return {"status": _aggregate_status(sub_results), **sub_results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--matrix-sizes", default="1024,2048,4096,8192")
    args = parser.parse_args()

    sizes = [int(s) for s in args.matrix_sizes.split(",")]
    result = run(sizes)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"status geral: {result['status']}")
        for key, value in result.items():
            if key == "status" or not isinstance(value, dict):
                continue
            print(f"{key}: {value.get('status')}")
            if value.get("detail"):
                print(f"  {value['detail']}")
            for run_result in value.get("runs", []):
                print(f"  {run_result}")

    return {"PASS": 0, "FAIL": 1}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
