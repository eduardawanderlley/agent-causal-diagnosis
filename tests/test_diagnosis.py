from causal_diagnosis import diagnose
from causal_diagnosis.metrics import hit_at_k, mean_reciprocal_rank
from support_agent.evaluation import replay_scenario, run_scenario
from support_agent.fixtures import TODAY
from support_agent.scenarios import build_scenarios


def _diagnose_with_replay(outcome):
    scenario = outcome.scenario
    return diagnose(
        outcome.spans,
        reference_date=TODAY,
        replay=lambda key, fix: replay_scenario(scenario, key, fix),
        accept=lambda verdict: verdict == scenario.expected_verdict,
    )


def _failures():
    outcomes = (run_scenario(s) for s in build_scenarios())
    return [o for o in outcomes if not o.passed]


def test_structural_heuristic_localizes_every_injected_root_cause():
    for outcome in _failures():
        diagnosis = diagnose(outcome.spans, reference_date=TODAY)
        root = outcome.scenario.root_cause_key
        assert diagnosis.heuristic_ranking[0] == root, (
            outcome.scenario.scenario_id,
            diagnosis.heuristic_ranking[:3],
        )


def test_counterfactual_confirms_the_top_candidate_for_every_failure():
    for outcome in _failures():
        diagnosis = _diagnose_with_replay(outcome)
        root = outcome.scenario.root_cause_key
        assert diagnosis.ranking[0] == root, outcome.scenario.scenario_id
        assert diagnosis.candidates and diagnosis.candidates[0].confirmed, outcome.scenario.scenario_id


def test_hit_at_k_and_mrr_on_a_small_example():
    rankings = [["a", "b", "c"], ["x", "y", "z"], ["p", "q", "r"]]
    truths = ["a", "y", "missing"]
    assert hit_at_k(rankings, truths, 1) == 1 / 3
    assert hit_at_k(rankings, truths, 2) == 2 / 3
    assert abs(mean_reciprocal_rank(rankings, truths) - (1 + 0.5 + 0) / 3) < 1e-9
