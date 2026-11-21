from causal_diagnosis import TraceGraph
from support_agent.evaluation import run_scenario
from support_agent.faults import FAULTS
from support_agent.scenarios import build_scenarios


def _scenario(scenario_id):
    return next(s for s in build_scenarios() if s.scenario_id == scenario_id)


def test_clean_runs_answer_correctly_for_every_order():
    clean = [s for s in build_scenarios() if s.fault == "none"]
    for scenario in clean:
        outcome = run_scenario(scenario)
        assert outcome.passed, f"{scenario.scenario_id} answered {outcome.verdict}"


def test_every_injected_fault_changes_the_outcome_somewhere():
    scenarios = build_scenarios()
    for fault in FAULTS[1:]:
        failing = [s for s in scenarios if s.fault == fault and not run_scenario(s).passed]
        assert failing, f"fault {fault} never produced a wrong answer"


def test_tool_steps_depend_on_their_decision_and_decisions_on_prior_tools():
    outcome = run_scenario(_scenario("none/PED-1001/t0"))
    graph = TraceGraph(outcome.spans)
    for key, step in graph.steps.items():
        if step.kind == "tool":
            assert step.depends_on == (key.replace(".tool", ".decision"),)
        else:
            prior_tools = {
                k for k, s in graph.steps.items() if s.kind == "tool" and s.index < step.index
            }
            assert set(step.depends_on) == prior_tools


def test_spans_do_not_leak_the_injected_fault():
    """Only the scenario label may name the fault; the diagnosis never reads it."""
    outcome = run_scenario(_scenario("stale_document/PED-1001/t0"))
    for span in outcome.spans:
        for name, value in span.attributes.items():
            assert "fault" not in name, (span.name, name)
            if name == "agent.scenario_id":
                continue
            for fault in FAULTS:
                assert fault not in str(value), (span.name, name, fault)


def test_faulted_runs_still_record_a_complete_trace():
    outcome = run_scenario(_scenario("prompt_drift/PED-1004/t0"))
    graph = TraceGraph(outcome.spans)
    assert graph.final_step() is not None
    assert graph.question.startswith("I want to return order PED-1004")
