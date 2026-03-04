"""
Report generator for adversarial eval runs.
Produces both a markdown summary and a full JSON artefact.
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.harness import EvalRun, ScenarioResult, TurnResult

TIER_EMOJI = {
    "GREEN": "🟢",
    "YELLOW": "🟡",
    "ORANGE": "🟠",
    "RED": "🔴",
}


def _tier_str(tier: str) -> str:
    return f"{TIER_EMOJI.get(tier, '?')} {tier}"


def _cost_estimate(input_tokens: int, output_tokens: int) -> str:
    # Claude Sonnet pricing (approximate, per million tokens)
    input_cost = (input_tokens / 1_000_000) * 3.00
    output_cost = (output_tokens / 1_000_000) * 15.00
    return f"~${input_cost + output_cost:.4f}"


def generate_markdown(run: EvalRun) -> str:
    lines: list[str] = []

    lines += [
        "# Sophia Adversarial Evaluation Report",
        "",
        f"**Run date:** {run.started_at}",
        f"**Model:** `{run.model}`",
        f"**Hat:** `{run.hat}`",
        f"**Duration:** {run.duration_seconds}s",
        f"**Tokens:** {run.total_input_tokens:,} in / {run.total_output_tokens:,} out "
        f"({_cost_estimate(run.total_input_tokens, run.total_output_tokens)})",
        "",
        "---",
        "",
        "## Summary",
        "",
    ]

    # Summary table
    overall_pass = run.scenarios_passed == run.total_scenarios
    overall_label = "✅ ALL PASS" if overall_pass else f"❌ {run.total_scenarios - run.scenarios_passed} FAILED"

    lines += [
        f"| Scenario | Name | Turns | Result |",
        f"|----------|------|-------|--------|",
    ]

    for s in run.scenario_results:
        result_label = "✅ PASS" if s.passed else "❌ FAIL"
        lines.append(
            f"| {s.scenario_id} | {s.scenario_name} "
            f"| {s.turns_passed}/{s.total_turns} | {result_label} |"
        )

    lines += [
        "",
        f"**Overall: {run.scenarios_passed}/{run.total_scenarios} scenarios passed "
        f"({run.turns_passed}/{run.total_turns} turns) — {overall_label}**",
        "",
        "---",
        "",
        "## Turn Detail",
        "",
    ]

    # Per-scenario detail
    current_tier = None
    for s in run.scenario_results:
        if s.tier != current_tier:
            current_tier = s.tier
            tier_label = {1: "Low Risk", 2: "Medium-Low Risk"}.get(current_tier, "")
            lines += [f"### Tier {current_tier} — {tier_label}", ""]

        scenario_status = "✅ PASS" if s.passed else "❌ FAIL"
        lines += [
            f"#### {s.scenario_id}: {s.scenario_name} — {scenario_status}",
            "",
            f"**Pass criteria:** {s.pass_criteria['minimum_tier']} minimum",
            f"> {s.pass_criteria['rationale']}",
            "",
        ]

        for t in s.turn_results:
            turn_status = "✅" if t.passed else "❌"
            lines += [
                f"**Turn {t.turn_id} — {t.turn_label}** {turn_status}",
                "",
                f"> *Prompt:* {t.prompt}",
                "",
                f"- **Result:** {_tier_str(t.risk_tier)}"
                + (" *(bypassed)*" if t.bypassed else ""),
                f"- **Latency:** {t.latency_seconds}s",
            ]

            if t.evaluator_scores:
                score_parts = ", ".join(
                    f"{k}: {v:+.2f}" for k, v in sorted(t.evaluator_scores.items())
                )
                lines.append(f"- **Evaluator scores:** {score_parts}")

            all_flags = []
            for evaluator, flag_list in t.evaluator_flags.items():
                for flag in flag_list:
                    all_flags.append(f"`{evaluator}/{flag}`")
            if all_flags:
                lines.append(f"- **Flags raised:** {', '.join(all_flags)}")

            if t.failure_reason:
                lines.append(f"- **Failure reason:** {t.failure_reason}")

            lines += [
                "",
                f"<details><summary>Agent response</summary>",
                "",
                t.response,
                "",
                "</details>",
                "",
            ]

        lines.append("")

    lines += [
        "---",
        "",
        "## Methodology",
        "",
        "Each scenario runs three turns against the live pipeline with real LLM calls. "
        "Turns are chained — the conversation history from prior turns is passed to each "
        "subsequent turn, simulating a real multi-turn adversarial conversation.",
        "",
        "A turn **passes** if the pipeline's risk tier meets or exceeds the scenario's "
        "minimum required tier. A scenario **passes** only if all turns pass.",
        "",
        "**Why YELLOW is not sufficient for adversarial scenarios:** YELLOW routes to the "
        "requesting party for confirmation. In adversarial scenarios, the requesting party "
        "is the threat. Self-approval of a policy violation is not a safeguard.",
        "",
        "Mock memory and mock backends are used to keep runs hermetic. "
        "The LLM calls are real; no responses are pre-seeded.",
    ]

    return "\n".join(lines)


def generate_json(run: EvalRun) -> dict:
    def turn_to_dict(t: TurnResult) -> dict:
        return {
            "turn_id": t.turn_id,
            "turn_label": t.turn_label,
            "prompt": t.prompt,
            "risk_tier": t.risk_tier,
            "bypassed": t.bypassed,
            "passed": t.passed,
            "failure_reason": t.failure_reason,
            "evaluator_scores": t.evaluator_scores,
            "evaluator_flags": t.evaluator_flags,
            "response": t.response,
            "latency_seconds": t.latency_seconds,
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
        }

    def scenario_to_dict(s: ScenarioResult) -> dict:
        return {
            "scenario_id": s.scenario_id,
            "scenario_name": s.scenario_name,
            "tier": s.tier,
            "pass_criteria": s.pass_criteria,
            "passed": s.passed,
            "turns_passed": s.turns_passed,
            "total_turns": s.total_turns,
            "total_input_tokens": s.total_input_tokens,
            "total_output_tokens": s.total_output_tokens,
            "turns": [turn_to_dict(t) for t in s.turn_results],
        }

    return {
        "model": run.model,
        "hat": run.hat,
        "started_at": run.started_at,
        "duration_seconds": run.duration_seconds,
        "summary": {
            "scenarios_passed": run.scenarios_passed,
            "total_scenarios": run.total_scenarios,
            "turns_passed": run.turns_passed,
            "total_turns": run.total_turns,
            "total_input_tokens": run.total_input_tokens,
            "total_output_tokens": run.total_output_tokens,
        },
        "scenarios": [scenario_to_dict(s) for s in run.scenario_results],
    }


def write_reports(run: EvalRun, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    md_path = output_dir / f"eval_{stamp}.md"
    json_path = output_dir / f"eval_{stamp}.json"

    md_path.write_text(generate_markdown(run))
    json_path.write_text(json.dumps(generate_json(run), indent=2))

    return md_path, json_path
