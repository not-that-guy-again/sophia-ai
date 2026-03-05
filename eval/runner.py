"""
CLI entry point for the Sophia adversarial evaluation suite.

Usage:
    # Run all scenarios
    uv run python eval/runner.py

    # Run only Tier 1
    uv run python eval/runner.py --tier 1

    # Run a single scenario
    uv run python eval/runner.py --scenario T2-1

    # Suppress report file output (print markdown to stdout only)
    uv run python eval/runner.py --no-save

Output files are written to eval/results/.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow imports from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.harness import run_eval
from eval.report import write_reports, generate_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sophia adversarial evaluation suite")
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2],
        default=None,
        help="Run only scenarios from a specific tier (1 or 2)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        metavar="ID",
        help="Run a single scenario by ID (e.g. T1-1, T2-3)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Print markdown report to stdout instead of saving to eval/results/",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()

    print("╔══════════════════════════════════════════════════════╗")
    print("║     SOPHIA ADVERSARIAL EVALUATION SUITE              ║")
    print("╚══════════════════════════════════════════════════════╝")

    try:
        run = await run_eval(
            tier_filter=args.tier,
            scenario_filter=args.scenario,
        )
    except RuntimeError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1

    print("\n" + "─" * 60)
    print(
        f"COMPLETE  {run.scenarios_passed}/{run.total_scenarios} scenarios passed  "
        f"({run.turns_passed}/{run.total_turns} turns)  "
        f"{run.duration_seconds}s"
    )
    print("─" * 60)

    if args.no_save:
        print("\n" + generate_markdown(run))
    else:
        output_dir = Path(__file__).parent / "results"
        md_path, json_path = write_reports(run, output_dir)
        print(f"\nReport:  {md_path}")
        print(f"JSON:    {json_path}")

    # Exit code 1 if any scenario failed — useful for CI
    return 0 if run.scenarios_passed == run.total_scenarios else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
