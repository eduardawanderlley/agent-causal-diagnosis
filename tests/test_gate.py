from support_agent.evaluation import run_gate
from support_agent.faults import DRIFTED_PROMPT_VERSION
from support_agent.planner import BASELINE_PROMPT_VERSION


def test_reference_configuration_passes_the_gate():
    report = run_gate(BASELINE_PROMPT_VERSION)
    assert report.passed, report


def test_drifted_prompt_is_blocked_by_the_gate():
    report = run_gate(DRIFTED_PROMPT_VERSION)
    assert not report.passed
    assert report.regressions
    assert report.clean_failures
