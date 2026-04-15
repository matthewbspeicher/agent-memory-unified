"""KalshiBench offline evaluation harness.

Runs `LLMClient.estimate_probability` over a dataset of resolved Kalshi
questions, then computes calibration metrics (Brier score, ECE) against
the known outcomes.

## Getting the dataset

The KalshiBench dataset (Saluda et al., Dec 2025 — arxiv 2512.16030) is
a public collection of 1,531 Kalshi questions with ground-truth
resolutions. Download from the paper's supplementary materials or
reconstruct from the Kalshi API using the question IDs in the paper.

Expected JSON format — a list of records, one per question:

    [
      {
        "question": "Will the Fed cut rates at the November meeting?",
        "resolution": "YES" | "NO",
        "category": "economics" (optional),
        "headlines": ["headline 1", ...] (optional; if absent, agent
                     will use its configured news sources at eval time)
      },
      ...
    ]

If `headlines` is absent, we pass an empty list — this measures the
model's prior on the question text alone, which is a more honest
baseline for a "no news available" scenario.

## Running

    PYTHONPATH=.:trading trading/.venv/bin/python -m eval.kalshi_bench \\
        --dataset /path/to/kalshibench.json \\
        --output reports/kalshi_bench_$(date +%F).json \\
        --limit 50  # smoke-test before running the full 1531

## Metrics interpretation

- **Brier score**: lower is better. Claude Opus 4.5 scored 0.227 in the
  paper. Superforecasters hit 0.12–0.15. Always-50% scores 0.25.
- **ECE**: expected calibration error. Lower is better.
  Superforecasters hit 0.03–0.05. 0.19 is the Claude base-model number
  before calibrated prompting.

Use this harness before deploying prompt changes to verify they don't
regress calibration. Stash the JSON output under `reports/` and diff
across runs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from eval.probability_metrics import calibration_report
from llm.client import LLMClient

logger = logging.getLogger("kalshi_bench")


def _load_dataset(path: Path) -> list[dict]:
    with path.open() as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list of records")
    return data


def _resolution_to_int(r: str) -> int:
    r = r.strip().upper()
    if r in ("YES", "Y", "1", "TRUE"):
        return 1
    if r in ("NO", "N", "0", "FALSE"):
        return 0
    raise ValueError(f"unrecognized resolution: {r!r}")


async def _score_one(
    llm: LLMClient, record: dict, ensemble_n: int
) -> tuple[float, int, str] | None:
    question = record.get("question")
    resolution = record.get("resolution")
    if not question or resolution is None:
        return None
    headlines = record.get("headlines") or []
    try:
        est = await llm.estimate_probability(
            question, headlines, ensemble_n=ensemble_n
        )
    except Exception as exc:
        logger.warning("estimate failed for %r: %s", question[:60], exc)
        return None
    try:
        outcome = _resolution_to_int(resolution)
    except ValueError as exc:
        logger.warning("bad resolution for %r: %s", question[:60], exc)
        return None
    return est.implied_probability, outcome, record.get("category", "uncategorized")


async def run_bench(
    dataset_path: Path,
    output_path: Path | None,
    *,
    limit: int | None = None,
    ensemble_n: int = 3,
    concurrency: int = 4,
) -> dict:
    records = _load_dataset(dataset_path)
    if limit:
        records = records[:limit]
    if not records:
        raise ValueError("dataset is empty after limit")

    llm = LLMClient(
        anthropic_key=os.environ.get("STA_ANTHROPIC_API_KEY"),
        groq_key=os.environ.get("STA_GROQ_API_KEY"),
        ollama_url=os.environ.get(
            "STA_OLLAMA_BASE_URL", "http://localhost:11434"
        ),
    )

    sem = asyncio.Semaphore(concurrency)

    async def _worker(rec: dict) -> tuple[float, int, str] | None:
        async with sem:
            return await _score_one(llm, rec, ensemble_n)

    results = await asyncio.gather(*(_worker(r) for r in records))
    scored = [r for r in results if r is not None]
    if not scored:
        raise RuntimeError(
            "all records failed to score — check dataset format and LLM config"
        )

    predictions = [p for p, _, _ in scored]
    outcomes = [y for _, y, _ in scored]
    report = calibration_report(predictions, outcomes)

    # Per-category breakdown (optional)
    by_category: dict[str, dict] = {}
    cats = {cat for _, _, cat in scored}
    for cat in cats:
        cat_preds = [p for p, _, c in scored if c == cat]
        cat_outs = [y for _, y, c in scored if c == cat]
        if len(cat_preds) >= 10:  # skip tiny buckets
            by_category[cat] = asdict(calibration_report(cat_preds, cat_outs))

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "n_records_attempted": len(records),
        "n_records_scored": len(scored),
        "ensemble_n": ensemble_n,
        "overall": asdict(report),
        "by_category": by_category,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
            json.dump(summary, f, indent=2)
        logger.info("report written to %s", output_path)

    return summary


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KalshiBench offline eval harness")
    parser.add_argument("--dataset", type=Path, required=True, help="JSON dataset path")
    parser.add_argument("--output", type=Path, default=None, help="output JSON report")
    parser.add_argument("--limit", type=int, default=None, help="limit to N records")
    parser.add_argument("--ensemble-n", type=int, default=3, help="ensemble size")
    parser.add_argument(
        "--concurrency", type=int, default=4, help="max parallel LLM calls"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    summary = asyncio.run(
        run_bench(
            args.dataset,
            args.output,
            limit=args.limit,
            ensemble_n=args.ensemble_n,
            concurrency=args.concurrency,
        )
    )

    overall = summary["overall"]
    print(f"\n=== KalshiBench Summary ===")
    print(f"n scored:              {overall['n']}")
    print(f"Brier score:           {overall['brier']:.4f}")
    print(f"ECE ({overall['bucket_count']} buckets):    {overall['ece']:.4f}")
    print(f"mean prediction:       {overall['mean_prediction']:.3f}")
    print(f"resolved YES rate:     {overall['resolved_yes_rate']:.3f}")
    if summary["by_category"]:
        print("\n--- per category ---")
        for cat, r in sorted(summary["by_category"].items()):
            print(f"  {cat:20s} n={r['n']:4d}  brier={r['brier']:.4f}  ece={r['ece']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
