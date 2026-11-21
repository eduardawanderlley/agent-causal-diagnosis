# Benchmark summary

Scenarios: 210, passed: 95 (45.2%), failures diagnosed: 115.

## Pass rate by fault

| Fault | Scenarios | Pass rate |
|---|---:|---:|
| `none` | 35 | 100.0% |
| `stale_document` | 35 | 57.1% |
| `silent_tool_error` | 35 | 14.3% |
| `extraction_corruption` | 35 | 14.3% |
| `context_truncation` | 35 | 14.3% |
| `prompt_drift` | 35 | 71.4% |

## Root-cause localization (failed runs only)

| Method | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| first_visible_error | 0.000 | 0.522 | 0.376 |
| last_before_final | 0.000 | 0.652 | 0.300 |
| structural_heuristic | 1.000 | 1.000 | 1.000 |
| heuristic_plus_counterfactual | 1.000 | 1.000 | 1.000 |

## Triage and cost

- Top candidate confirmed by counterfactual replay: 100.0%
- Average replays per diagnosed failure: 1.26
- Failures answered with a wrong, confident verdict: 25
- Failures that were escalated instead: 90
