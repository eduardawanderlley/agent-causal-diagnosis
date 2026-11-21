# Methodology

## The problem

Given one run of an agent that produced a wrong answer, find the step whose correction would have produced a right one, and check that claim by actually making the correction.

Two parts of that sentence matter. The first is that the target is the root cause, not the symptom. The step where the error becomes visible is often a long way downstream of where it was introduced. The second is that the claim is tested. A ranked list of suspicious spans is a hypothesis. A candidate becomes a diagnosis only when the corrected run succeeds.

## Causal graph

Each step records the steps it consumed in `agent.depends_on`. Together these form a directed acyclic graph whose edges mean "this output was an input to that step". Starting from the final decision, the diagnosis collects every ancestor and considers each one as a possible cause, plus the final decision itself, since a faulty decision can be the final one.

## Signals

Each detector looks at one step and returns evidence. Weights are small integers and are summed per step. The detectors encode knowledge about this agent's tools, which is the part that would need rewriting for a different system.

| Signal | Applies to | Weight | What it detects | Correction tried |
|---|---|---:|---|---|
| `explicit_tool_error` | lookup_order | 1 | Tool returned `status: error` | `refetch_order` |
| `silent_tool_error` | lookup_order | 3 | Tool returned `status: ok` with an error payload | `refetch_order` |
| `stale_document` | search_policy | 3 | A retrieved document is older than 365 days | `refresh_policy_index` |
| `missing_policy_terms` | search_policy | 2 | The retrieved text has no parseable return window | `refresh_policy_index` |
| `ungrounded_identifier` | decision | 3 | An order identifier in the action appears in neither the question nor any upstream result | `ground_identifier_args` |
| `skipped_required_step` | final decision | 3 | A verdict was given although the policy window was known and no deadline was calculated | `restore_deadline_step` |

The weight of a step is the sum of its signals, and its correction is the one attached to its strongest signal. Ties in score go to the earlier step.

Two of these signals are worth explaining. `ungrounded_identifier` checks identifier arguments only, not free text. Free-text arguments such as an escalation summary are expected to contain words that aren't in the question, so checking them would only produce noise. `skipped_required_step` is the signal that catches prompt drift. It fires on the step where the verdict was reached without the calculation, which is the step where the drift took effect, not the later step where the wrong answer is visible.

## Ranking

Candidates are sorted by score, then by execution order. This is the structural heuristic. It runs with no LLM, no replay and no external data, and it's fast enough to run on every failure.

When no candidate has any signal, the fallback ranking is simply the steps in execution order, earliest first. That's the least-presumptuous answer when the detectors have nothing to say.

## Counterfactual confirmation

For the top k candidates (k = 3 by default), the system re-runs the same input with the candidate step's output replaced by its correction. The replayed verdict is checked against the verifier. Confirmed candidates move to the front of the ranking, preserving their heuristic order among themselves.

Corrections use source-of-truth data. `refetch_order` calls the order store directly. `refresh_policy_index` runs retrieval against the current index. `ground_identifier_args` takes the identifier from the user's message. `restore_deadline_step` recomputes the deadline from the observed inputs. None of them consult the injected fault, and none of them are used for ranking, only for testing a hypothesis.

The verifier is the part that needs care. In this benchmark it is the ground-truth expectation. In a real system it has to be something independent of the agent: a deterministic recomputation from source data, a rule, or a human label. If there isn't one, confirmation isn't possible, and the honest output is the heuristic ranking with no confirmation.

## Metrics

Hit@k is the share of failed runs whose true root cause appears in the top k of the ranking. MRR is the mean reciprocal rank of the true root cause, with zero when it's absent. Both are computed over failed runs only, since a passing run has no failure to localize.

Two naive baselines give the numbers context. The first treats the earliest step that reports an explicit error as the cause. That's what a team following error logs would do first. The second treats the steps nearest the answer as the most likely cause, which is what a reader scanning the trace backwards would do. Both are cheap and both are wrong often enough to be useful as reference points.

## Failure taxonomy

| Fault | Origin | How it surfaces | Root-cause step |
|---|---|---|---|
| `stale_document` | Retrieval returns an outdated policy | Wrong window, so a wrong verdict | `1.tool` |
| `silent_tool_error` | Order lookup reports success with an error payload | Missing data, so escalation | `0.tool` |
| `extraction_corruption` | Planner produces an order identifier with two digits swapped | Lookup fails, so escalation | `0.decision` |
| `context_truncation` | Retrieved text is cut before the window | No window found, so escalation | `1.tool` |
| `prompt_drift` | Prompt skips the deadline calculator | Wrong verdict from a fixed window | `2.decision` |

Each fault's root step is the step where it originates. That's the ground truth. The step where it surfaces is often later, and locating the origin rather than the surface is the point of the exercise.

## Regression gate

The gate runs the full suite under two configurations: the reference, and the candidate under review. A regression is any scenario the reference answers correctly that the candidate gets wrong. A candidate is also rejected if any fault-free scenario is wrong, since a clean run failing is never acceptable regardless of what the reference did.

The gate doesn't need a stored baseline file. It recomputes the reference each time, so it can't drift out of date. The cost is a few hundred extra agent runs, which take well under a second here.

## Threats to validity

The faults are constructed by me and cover the failure modes I chose. The signals were written with those faults in view, which inflates localization numbers. The honest test is a fault class the signals don't target, and that's the first item on the roadmap.

The verifier and the ground truth are the same thing in the benchmark. That makes confirmation look stronger than it would be if the verifier were independent of the expected answers. The fixtures are small, so the policy logic is simple enough to be checked by hand.

Timing measurements depend on the environment and on the exporter, so they're recorded in the JSON output and deliberately left out of the summary table.
