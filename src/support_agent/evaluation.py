"""Helpers shared by the benchmark, the regression gate and the tests."""

from __future__ import annotations

from dataclasses import dataclass

from .agent import SupportAgent
from .interventions import FIXES
from .planner import BASELINE_PROMPT_VERSION
from .scenarios import Scenario, build_scenarios


@dataclass(frozen=True)
class Outcome:
    scenario: Scenario
    verdict: str
    passed: bool
    spans: tuple  # finished OpenTelemetry spans of this one run


def run_scenario(scenario: Scenario, prompt_version: str = BASELINE_PROMPT_VERSION) -> Outcome:
    agent = SupportAgent(prompt_version=prompt_version)
    result = agent.run(scenario.question, fault=scenario.fault, scenario_id=scenario.scenario_id)
    spans = tuple(
        span for span in agent.exporter.get_finished_spans() if span.context.trace_id == result.trace_id
    )
    return Outcome(
        scenario=scenario,
        verdict=result.verdict,
        passed=result.verdict == scenario.expected_verdict,
        spans=spans,
    )


def replay_scenario(scenario: Scenario, key: str, fix_name: str,
                    prompt_version: str = BASELINE_PROMPT_VERSION) -> str:
    """Re-run the same scenario with one step replaced by a known-good fix."""
    agent = SupportAgent(prompt_version=prompt_version)
    result = agent.run(
        scenario.question,
        fault=scenario.fault,
        interventions={key: FIXES[fix_name]},
        scenario_id=scenario.scenario_id,
    )
    return result.verdict


def run_suite(prompt_version: str = BASELINE_PROMPT_VERSION,
              scenarios: list[Scenario] | None = None) -> dict[str, bool]:
    scenarios = build_scenarios() if scenarios is None else scenarios
    return {s.scenario_id: run_scenario(s, prompt_version).passed for s in scenarios}


@dataclass(frozen=True)
class GateReport:
    regressions: tuple[str, ...]
    clean_failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.regressions and not self.clean_failures


def run_gate(candidate_prompt_version: str, scenarios: list[Scenario] | None = None) -> GateReport:
    """Compare a candidate configuration against the reference one.

    A candidate fails if it breaks any scenario the reference handles correctly,
    or if it gets any fault-free scenario wrong.
    """
    scenarios = build_scenarios() if scenarios is None else scenarios
    reference = run_suite(BASELINE_PROMPT_VERSION, scenarios)
    candidate = run_suite(candidate_prompt_version, scenarios)
    regressions = tuple(sorted(sid for sid, ok in reference.items() if ok and not candidate[sid]))
    clean_failures = tuple(sorted(sid for sid, ok in candidate.items() if sid.startswith("none/") and not ok))
    return GateReport(regressions=regressions, clean_failures=clean_failures)
