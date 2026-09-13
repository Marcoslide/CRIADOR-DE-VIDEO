"""CLI do GPU Engine (seção 34 da missão) — `dhf-gpu health|status|capabilities|benchmark|report`.

    uv run --project services/gpu_engine dhf-gpu health
    uv run --project services/gpu_engine dhf-gpu status --json
    uv run --project services/gpu_engine dhf-gpu benchmark gpu --json
    uv run --project services/gpu_engine dhf-gpu report --out infra/gpu/reports

Saída em texto (default) ou --json/--markdown conforme o subcomando.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dhf_gpu_engine.orchestrator import GpuOrchestrator

DEFAULT_VRAM_TOTAL_MB = 24576.0  # RTX 4090 — ver infra/gpu/config/gpu-engine.example.env


def _build_orchestrator(args: argparse.Namespace) -> GpuOrchestrator:
    return GpuOrchestrator(vram_total_mb=getattr(args, "vram_total_mb", DEFAULT_VRAM_TOTAL_MB))


def _cmd_health(args: argparse.Namespace) -> int:
    orchestrator = _build_orchestrator(args)
    health = orchestrator.get_health()
    if args.json:
        print(json.dumps(health, indent=2, ensure_ascii=False))
    else:
        print(f"[{health['status']}] {health['detail']}")
    return {"PASS": 0, "FAIL": 1}.get(health["status"], 2)


def _cmd_status(args: argparse.Namespace) -> int:
    orchestrator = _build_orchestrator(args)
    status = orchestrator.get_status()
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        gpu = status["gpu"]
        print(f"GPU: {gpu.get('gpu_model') or 'não detectada'} — status: {gpu['status']}")
        vram = status["vram"]
        print(f"VRAM: {vram['allocated_mb']:.0f}/{vram['total_mb']:.0f} MB ({vram['status']})")
    return 0 if status["gpu"]["status"] == "connected" else 2


def _cmd_capabilities(args: argparse.Namespace) -> int:
    orchestrator = _build_orchestrator(args)
    caps = orchestrator.get_capabilities()
    print(json.dumps(caps.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0 if caps.status.value == "connected" else 2


def _cmd_benchmark(args: argparse.Namespace) -> int:
    orchestrator = _build_orchestrator(args)
    result = orchestrator.run_benchmark(args.name, timeout=args.timeout)
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    else:
        print(f"[{result.status.value}] {args.name}: {result.detail or ''}")
    return {"PASS": 0, "FAIL": 1}.get(result.status.value, 2)


def _cmd_report(args: argparse.Namespace) -> int:
    from dhf_gpu_engine.reports import write_report

    results_file = Path(args.results) if args.results else None
    json_path, md_path = write_report(Path(args.out), results_file)
    print(f"Relatório JSON: {json_path}")
    print(f"Relatório Markdown: {md_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dhf-gpu", description="GPU Engine CLI — RTX 4090 studio node"
    )
    parser.add_argument("--vram-total-mb", type=float, default=DEFAULT_VRAM_TOTAL_MB)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_health = subparsers.add_parser("health", help="veredito agregado PASS/WARN/FAIL/REQUIRES_GPU")
    p_health.add_argument("--json", action="store_true")
    p_health.set_defaults(func=_cmd_health)

    p_status = subparsers.add_parser("status", help="status de GPU + VRAM")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=_cmd_status)

    p_caps = subparsers.add_parser(
        "capabilities", help="todas as capabilities detectadas (sempre JSON)"
    )
    p_caps.set_defaults(func=_cmd_capabilities)

    p_bench = subparsers.add_parser("benchmark", help="roda um benchmark de infra/gpu/benchmarks/")
    p_bench.add_argument("name", choices=["gpu", "vram", "nvenc", "disk"])
    p_bench.add_argument("--json", action="store_true")
    p_bench.add_argument("--timeout", type=float, default=60.0)
    p_bench.set_defaults(func=_cmd_benchmark)

    p_report = subparsers.add_parser("report", help="gera GPU_ENGINE_REPORT_<timestamp>.json/.md")
    p_report.add_argument("--out", default="infra/gpu/reports")
    p_report.add_argument(
        "--results", default=None, help="GPU_ENGINE_RESULTS_FILE dos scripts bash"
    )
    p_report.set_defaults(func=_cmd_report)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
