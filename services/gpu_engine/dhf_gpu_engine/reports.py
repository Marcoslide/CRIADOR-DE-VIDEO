"""Geração de relatório (seção 35 da missão): GPU_ENGINE_REPORT_<timestamp>.json/.md com
hardware, software, versões, testes, métricas, warnings e falhas. Consome tanto o
resultado estruturado deste pacote (GpuCapabilities/TelemetrySnapshot) quanto o arquivo
de resultados gerado pelos scripts bash de infra/gpu/ (GPU_ENGINE_RESULTS_FILE, um JSON
por linha) — uma única fonte de verdade para o relatório final, sem duplicar o que os
scripts bash já checaram.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dhf_gpu_engine.capabilities import detect_capabilities
from dhf_gpu_engine.telemetry import collect_telemetry


def _read_bash_results(results_file: Path | None) -> list[dict[str, Any]]:
    if results_file is None or not results_file.exists():
        return []
    rows = []
    for line in results_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def build_report(results_file: Path | None = None) -> dict[str, Any]:
    caps = detect_capabilities()
    telemetry = collect_telemetry()
    bash_results = _read_bash_results(results_file)

    counts = Counter(row["status"] for row in bash_results)
    fails = [row for row in bash_results if row["status"] == "FAIL"]
    warns = [row for row in bash_results if row["status"] == "WARN"]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "hardware": {
            "gpu_model": caps.gpu_model,
            "vram_total_mb": caps.vram_total_mb,
            "cuda_capability": caps.cuda_capability,
        },
        "software": {
            "driver_version": caps.driver_version,
            "cuda_version": caps.cuda_version,
            "tensorrt_version": caps.tensorrt_version,
            "nvenc_codecs": caps.nvenc_codecs,
        },
        "gpu_status": caps.status.value,
        "checks_summary": dict(counts),
        "failures": fails,
        "warnings": warns,
        "telemetry": telemetry.model_dump(mode="json"),
        "all_checks": bash_results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# GPU Engine Report — {report['generated_at']}",
        "",
        "## Hardware",
        f"- GPU: {report['hardware']['gpu_model'] or 'não detectada'}",
        f"- VRAM total: {report['hardware']['vram_total_mb'] or 'desconhecida'} MB",
        f"- Compute capability: {report['hardware']['cuda_capability'] or 'desconhecida'}",
        "",
        "## Software",
        f"- Driver: {report['software']['driver_version'] or 'não detectado'}",
        f"- CUDA Toolkit: {report['software']['cuda_version'] or 'não detectado'}",
        f"- TensorRT: {report['software']['tensorrt_version'] or 'não detectado'}",
        f"- NVENC: {', '.join(report['software']['nvenc_codecs']) or 'nenhum codec detectado'}",
        "",
        f"## Status geral da GPU: `{report['gpu_status']}`",
        "",
        "## Resumo das checagens",
    ]
    for status, count in sorted(report["checks_summary"].items()):
        lines.append(f"- {status}: {count}")

    if report["failures"]:
        lines.append("\n## Falhas")
        for row in report["failures"]:
            lines.append(f"- **[{row.get('script')}] {row.get('name')}**: {row.get('detail')}")

    if report["warnings"]:
        lines.append("\n## Avisos")
        for row in report["warnings"]:
            lines.append(f"- [{row.get('script')}] {row.get('name')}: {row.get('detail')}")

    return "\n".join(lines) + "\n"


def write_report(output_dir: Path, results_file: Path | None = None) -> tuple[Path, Path]:
    """Escreve GPU_ENGINE_REPORT_<timestamp>.json e .md em `output_dir`, retornando os
    dois caminhos escritos."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(results_file)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    json_path = output_dir / f"GPU_ENGINE_REPORT_{timestamp}.json"
    md_path = output_dir / f"GPU_ENGINE_REPORT_{timestamp}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    md_path.write_text(render_markdown(report))

    return json_path, md_path
