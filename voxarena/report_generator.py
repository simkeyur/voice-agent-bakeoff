import os
import glob
from typing import Any, Callable, Optional
from loguru import logger
from voxarena.config import settings
from voxarena.manifest import RunManifest
from voxarena.providers import provider_names


def _safe_mean(values: list[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def _stats_for(runs: list[RunManifest]) -> dict[str, Any]:
    ttfa = _safe_mean([r.metrics.average_ttfa_ms for r in runs])
    accuracy = _safe_mean([r.metrics.tool_call_accuracy_rate for r in runs])
    interruption = _safe_mean([r.metrics.average_interruption_stop_latency_ms for r in runs])
    halls = [r.metrics.hallucination_count or 0 for r in runs]
    avg_hall = sum(halls) / len(halls) if halls else 0.0
    return {
        "count": len(runs),
        "avg_ttfa_ms": ttfa,
        "avg_accuracy": accuracy,
        "avg_interruption_ms": interruption,
        "avg_hallucinations": avg_hall,
    }


def _fmt(value: Optional[float], suffix: str = "", precision: int = 0) -> str:
    return f"{value:.{precision}f}{suffix}" if value is not None else "—"


def _winner(stats_by_provider: dict[str, dict[str, Any]], metric: str, lower_is_better: bool) -> str:
    candidates = [(p, s[metric]) for p, s in stats_by_provider.items() if s[metric] is not None]
    if not candidates:
        return "—"
    winner = min(candidates, key=lambda x: x[1]) if lower_is_better else max(candidates, key=lambda x: x[1])
    return winner[0]


def generate_report() -> None:
    logger.info("Generating comparative markdown report...")
    manifest_files = glob.glob(
        os.path.join(settings.RESULTS_DIR, "**", "manifest.json"), recursive=True
    )

    runs: list[RunManifest] = []
    for file_path in manifest_files:
        try:
            manifest = RunManifest.load(file_path)
            if manifest.status == "completed":
                runs.append(manifest)
        except Exception as e:
            logger.error(f"Failed to load manifest at {file_path}: {e}")

    # Group by provider — include every registered provider so the table is consistent,
    # even if a provider has zero completed runs.
    providers = provider_names()
    grouped: dict[str, list[RunManifest]] = {p: [] for p in providers}
    for r in runs:
        grouped.setdefault(r.provider, []).append(r)

    stats_by_provider = {p: _stats_for(rs) for p, rs in grouped.items()}

    # Build the comparison table
    header = "| Provider | Runs | Avg TTFA | Tool Accuracy | Interruption | Hallucinations |"
    divider = "| --- | --- | --- | --- | --- | --- |"
    rows = [
        f"| {p} | {s['count']} "
        f"| {_fmt(s['avg_ttfa_ms'], ' ms')} "
        f"| {_fmt((s['avg_accuracy'] or 0) * 100, '%', 1) if s['avg_accuracy'] is not None else '—'} "
        f"| {_fmt(s['avg_interruption_ms'], ' ms')} "
        f"| {_fmt(s['avg_hallucinations'], ' per run', 1)} |"
        for p, s in stats_by_provider.items()
    ]
    comparison_table = "\n".join([header, divider, *rows])

    # Per-metric winners (only meaningful if at least 2 providers have data)
    populated = {p: s for p, s in stats_by_provider.items() if s["count"] > 0}
    if len(populated) >= 2:
        winners = (
            f"- **Lowest TTFA:** `{_winner(populated, 'avg_ttfa_ms', lower_is_better=True)}`\n"
            f"- **Highest tool accuracy:** `{_winner(populated, 'avg_accuracy', lower_is_better=False)}`\n"
            f"- **Lowest interruption latency:** `{_winner(populated, 'avg_interruption_ms', lower_is_better=True)}`\n"
            f"- **Fewest hallucinations:** `{_winner(populated, 'avg_hallucinations', lower_is_better=True)}`"
        )
    else:
        winners = "_Not enough providers with completed runs to declare per-metric winners._"

    analysis_dir = os.path.join(settings.BASE_DIR, "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    report_path = os.path.join(analysis_dir, "report.md")

    report_content = f"""# VoxArena Comparative Report

Head-to-head comparison of registered realtime voice providers across all completed runs in `results/`.

## Comparison Table

{comparison_table}

## Per-Metric Winners

{winners}

## Metric Definitions

- **Avg TTFA** — mean time-to-first-audio in milliseconds. Lower is better.
- **Tool Accuracy** — percentage of expected tool calls that were correctly invoked.
- **Interruption** — mean time the bot kept speaking after the user interrupted. Lower is better.
- **Hallucinations** — mean number of hallucinated facts per run (graded against ground-truth knowledge base).

## Detailed Run Reference

For comprehensive logs, consult the run manifests directly under `results/<provider>/<run_id>/manifest.json`.
"""

    with open(report_path, "w") as f:
        f.write(report_content)

    logger.success(f"Report compiled successfully at {report_path}")


if __name__ == "__main__":
    generate_report()
