"""Benchmark for causal localization and counterfactual confirmation.

Runs every scenario, diagnoses each failure from its spans alone, and scores
the rankings against the injected ground truth. Two naive baselines are
included so the numbers have something to be compared with.

    python benchmarks/run_benchmark.py

Writes benchmarks/results/summary.json and benchmarks/results/summary.md.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

from causal_diagnosis import baseline_rankings, diagnose
from causal_diagnosis.metrics import hit_at_k, mean_reciprocal_rank
from support_agent.evaluation import replay_scenario, run_scenario
from support_agent.faults import FAULTS
from support_agent.fixtures import TODAY
from support_agent.scenarios import build_scenarios

RESULTS_DIR = Path(__file__).resolve().parent / "results"
METHODS = ("first_visible_error", "last_before_final", "structural_heuristic", "heuristic_plus_counterfactual")


def evaluate() -> tuple[dict, list[dict]]:
    scenarios = build_scenarios()
    per_fault: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    failures: list[dict] = []

    for scenario in scenarios:
        per_fault[scenario.fault]["total"] += 1
        outcome = run_scenario(scenario)
        if outcome.passed:
            per_fault[scenario.fault]["passed"] += 1
            continue

        started = time.perf_counter()
        diagnosis = diagnose(
            outcome.spans,
            reference_date=TODAY,
            replay=lambda key, fix, s=scenario: replay_scenario(s, key, fix),
            accept=lambda verdict, s=scenario: verdict == s.expected_verdict,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        baselines = baseline_rankings(outcome.spans)

        failures.append({
            "scenario_id": scenario.scenario_id,
            "fault": scenario.fault,
            "root": scenario.root_cause_key,
            "verdict": outcome.verdict,
            "expected": scenario.expected_verdict,
            "rankings": {
                "first_visible_error": baselines["first_visible_error"],
                "last_before_final": baselines["last_before_final"],
                "structural_heuristic": diagnosis.heuristic_ranking,
                "heuristic_plus_counterfactual": diagnosis.ranking,
            },
            "top_confirmed": bool(diagnosis.candidates and diagnosis.candidates[0].confirmed),
            "replays": diagnosis.replays,
            "diagnosis_ms": elapsed_ms,
        })

    return summarize(scenarios, per_fault, failures), failures


def summarize(scenarios, per_fault, failures) -> dict:
    truths = [f["root"] for f in failures]
    localization = {}
    for method in METHODS:
        rankings = [f["rankings"][method] for f in failures]
        localization[method] = {
            "hit@1": round(hit_at_k(rankings, truths, 1), 3),
            "hit@3": round(hit_at_k(rankings, truths, 3), 3),
            "mrr": round(mean_reciprocal_rank(rankings, truths), 3),
        }

    total = len(scenarios)
    passed = sum(v["passed"] for v in per_fault.values())
    wrong_answers = sum(1 for f in failures if f["verdict"] != "escalated")
    return {
        "scenarios": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3),
        "by_fault": {
            fault: {
                "scenarios": per_fault[fault]["total"],
                "pass_rate": round(per_fault[fault]["passed"] / per_fault[fault]["total"], 3),
            }
            for fault in FAULTS
        },
        "failures": len(failures),
        "failures_answered_wrongly": wrong_answers,
        "failures_escalated": len(failures) - wrong_answers,
        "localization": localization,
        "counterfactual_top1_confirmed": round(
            sum(f["top_confirmed"] for f in failures) / len(failures), 3
        ) if failures else 0.0,
        "avg_replays_per_failure": round(statistics.mean(f["replays"] for f in failures), 2),
        "median_diagnosis_ms": round(statistics.median(f["diagnosis_ms"] for f in failures), 2),
    }


def render_markdown(summary: dict) -> str:
    lines = [
        "# Benchmark summary",
        "",
        f"Scenarios: {summary['scenarios']}, passed: {summary['passed']} "
        f"({summary['pass_rate']:.1%}), failures diagnosed: {summary['failures']}.",
        "",
        "## Pass rate by fault",
        "",
        "| Fault | Scenarios | Pass rate |",
        "|---|---:|---:|",
    ]
    for fault, stats in summary["by_fault"].items():
        lines.append(f"| `{fault}` | {stats['scenarios']} | {stats['pass_rate']:.1%} |")

    lines += [
        "",
        "## Root-cause localization (failed runs only)",
        "",
        "| Method | Hit@1 | Hit@3 | MRR |",
        "|---|---:|---:|---:|",
    ]
    for method, metrics in summary["localization"].items():
        lines.append(f"| {method} | {metrics['hit@1']:.3f} | {metrics['hit@3']:.3f} | {metrics['mrr']:.3f} |")

    lines += [
        "",
        "## Triage and cost",
        "",
        f"- Top candidate confirmed by counterfactual replay: {summary['counterfactual_top1_confirmed']:.1%}",
        f"- Average replays per diagnosed failure: {summary['avg_replays_per_failure']}",
        f"- Failures answered with a wrong, confident verdict: {summary['failures_answered_wrongly']}",
        f"- Failures that were escalated instead: {summary['failures_escalated']}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    summary, _ = evaluate()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (args.out / "summary.md").write_text(render_markdown(summary), encoding="utf-8")
    print(render_markdown(summary))


if __name__ == "__main__":
    main()
