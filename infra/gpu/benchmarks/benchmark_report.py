#!/usr/bin/env python3
"""benchmark_report.py — wrapper fino sobre dhf_gpu_engine.reports (services/gpu_engine),
para ser chamável diretamente de dentro de infra/gpu/ sem duplicar a lógica de geração
de relatório (seção 35 da missão). Requer o workspace uv sincronizado
(`uv sync --all-packages` na raiz do monorepo).

Uso:
    python3 benchmark_report.py [--out infra/gpu/reports] [--results /tmp/gpu-engine-results.jsonl]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="infra/gpu/reports")
    parser.add_argument("--results", default=None)
    args = parser.parse_args()

    try:
        from dhf_gpu_engine.reports import write_report
    except ImportError:
        print(
            "[NOT_TESTED] pacote dhf_gpu_engine não encontrado no ambiente Python atual.\n"
            "Rode via: uv run --project services/gpu_engine python "
            + str(Path(__file__).resolve())
            + " [...]\n"
            "ou simplesmente: uv run --project services/gpu_engine dhf-gpu report [...]",
            file=sys.stderr,
        )
        return 2

    results_file = Path(args.results) if args.results else None
    json_path, md_path = write_report(Path(args.out), results_file)
    print(f"Relatório JSON: {json_path}")
    print(f"Relatório Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
