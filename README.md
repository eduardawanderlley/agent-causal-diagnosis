# agent-causal-diagnosis

Find the step that caused an LLM agent to give a wrong answer, prove it by replaying the run with that step corrected, and block the same regression from coming back in CI.

Tracing tools show what an agent did. On a run with ten tool calls and a couple of sub-agents, the error is usually visible at the last step and caused several steps earlier: a tool returned stale data at step two, the model reasoned correctly on top of it for four steps, and the wrong answer only surfaced at step eight. A dashboard can show you the wrong answer. It can't tell you which decision to change, and it can't tell you whether changing it would have helped.

This repository is a small but complete version of an approach that answers both questions. It contains a customer-support agent instrumented with OpenTelemetry, a set of controlled faults with known root causes, a diagnosis that ranks candidate causes from the spans alone, a counterfactual replay that accepts a cause only when fixing it makes the answer correct, and a regression gate that fails the build when a prompt or model change reintroduces a known failure.

## What's in the box

The agent has four tools (order lookup, policy search over a small index, deadline calculation and ticket escalation) and a decision loop. Every decision and every tool call is an OpenTelemetry span that records its inputs, its outputs and the steps it depended on. That last part is what makes causal analysis possible.

Faults are injected at the boundary between the agent and its environment. There are five of them, each modelled on a failure I have seen in real support systems: a stale policy document, a tool that reports success with an error payload, a corrupted order identifier, truncated retrieval context and a prompt that drifts. Tools and planner stay clean, and the diagnosis never sees which fault was active.

The diagnosis builds a dependency graph from the spans, scores every upstream step with anomaly signals, and ranks the candidates. It reads spans and nothing else, so it works on any trace that follows the same schema. The counterfactual step replays the top candidates with a known-good correction for that one step and confirms a candidate only if the corrected run gives the right answer.

The regression gate runs the full scenario suite under a reference configuration and under a candidate one, and fails if the candidate breaks anything the reference gets right, or gets a fault-free case wrong.

## Quick start

```bash
git clone https://github.com/<your-username>/agent-causal-diagnosis.git
cd agent-causal-diagnosis
python -m venv .venv && source .venv/bin/activate
make install      # package plus dev dependencies
make test         # agent behaviour, localization, metrics and the gate
make benchmark    # 210 scenarios, writes benchmarks/results/
make gate         # CI gate against the reference configuration
```

Run a single request, with and without the drifted prompt:

```bash
python -m support_agent "Can I still return PED-1004?"
python -m support_agent "Can I still return PED-1004?" --fault prompt_drift
```

The reference agent answers `eligible`. The drifted one answers `not_eligible`. The order was delivered 18 days ago and the electronics window is 30, so the second answer is wrong. The trace shows the reason: the drifted prompt skipped the deadline calculation and reasoned with a fixed 15-day window.

## Results

The benchmark runs 210 scenarios: 7 orders, 5 phrasings and 6 fault settings. 115 of them end with a verdict that doesn't match the expected one, either a wrong answer or an escalation. Each of those is diagnosed from its spans and then checked by replay.

| Method | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| First visible error (naive baseline) | 0.000 | 0.522 | 0.376 |
| Nearest steps before the answer (naive baseline) | 0.000 | 0.652 | 0.300 |
| Structural heuristic | 1.000 | 1.000 | 1.000 |
| Heuristic plus counterfactual confirmation | 1.000 | 1.000 | 1.000 |

The full breakdown, including pass rate by fault, is in `benchmarks/results/summary.md`.

Read these numbers with the right caveats. The structural heuristic is perfect on this suite largely because each injected fault leaves a signature that the signal library was written to detect. That shows the pipeline works end to end. It does not show that the heuristic generalizes to failures it wasn't designed for, and that is the first thing I would test next. The counterfactual step confirmed the top candidate in every failure, so it didn't change the ranking here; its job is to reject a wrong cause when the heuristic produces one, and this suite never does.

The triage numbers matter as much as the localization ones. Of the 115 failures, 90 were escalated to a human, and 25 produced a confident wrong answer, all of them from stale documents or prompt drift. The gate exists for exactly that second group: a change that quietly moves failures from "escalated" to "wrong and confident" is a regression even when the pass rate looks fine.

## How the diagnosis works

The full method is in [docs/methodology.md](docs/methodology.md). The short version: starting from the step where the answer went wrong, walk upstream through the dependency edges. At each step, run a set of detectors. A stale document, an error hidden inside a success status, an identifier that appears nowhere in the user's message or the retrieved evidence, a verdict given without a required calculation: each one adds weight to that step. Candidates are ranked by total weight, with ties broken toward the earliest step, since an earlier cause explains more downstream behaviour.

Then comes the part that turns a hypothesis into evidence. For each of the top three candidates, the system re-runs the same input with a known-good correction for that one step, using source-of-truth data. If the corrected run produces the right answer, the candidate is confirmed. If not, it's demoted.

## Connecting to Langfuse and LangSmith

The agent never talks to either platform directly. It exports OTLP to a collector, and the collector fans the same traces out to both.

```bash
cp deploy/.env.example deploy/.env      # fill in your keys
set -a; source deploy/.env; set +a
docker run --rm -p 4318:4318 \
  --env-file deploy/.env \
  -v "$(pwd)/deploy/otel-collector.yaml:/etc/otelcol-contrib/config.yaml" \
  otel/opentelemetry-collector-contrib:latest

pip install -e ".[otlp]"
python -m support_agent "Can I still return PED-1004?"
```

Check the endpoints and header formats in the Langfuse and LangSmith OpenTelemetry docs before you rely on them; both vendors change them from time to time.

## Project layout

```
src/
  support_agent/        the agent, tools, planner, fault injection, scenarios
    agent.py            decision loop with one span per decision and per tool call
    planner.py          rule-based planner (stands in for the LLM decision step)
    faults.py           controlled faults, applied at the agent boundary
    interventions.py    known-good corrections used by counterfactual replay
    scenarios.py        the 210-scenario suite and its ground truth
    evaluation.py       shared run, replay and gate helpers
  causal_diagnosis/     reads spans only; no dependency on the agent
    graph.py            steps and dependency edges, built from spans
    signals.py          anomaly detectors and their weights
    localize.py         ranking, baselines and the diagnose() entry point
    counterfactual.py   replay-based confirmation
    metrics.py          Hit@k and MRR
tests/                  agent behaviour, diagnosis quality, gate behaviour
benchmarks/             benchmark runner and committed results
scripts/                regression gate for CI
deploy/                 OpenTelemetry Collector config and env template
docs/                   architecture and methodology
```

## Limitations

The faults are injected by me, so the failure modes are the ones I thought of. Real failures are messier and combine in ways a suite like this doesn't cover.

The planner is rule-based, which keeps every run deterministic and free. An LLM-backed planner would make the replay more involved: you'd replay with recorded model outputs rather than re-running the planner from scratch. That's described in the methodology doc and isn't implemented yet.

Counterfactual confirmation needs a verifier, meaning something that can tell whether the corrected answer is right. In this benchmark that's the ground truth. In production it has to be a deterministic check that recomputes the answer from source data, or a labelled expectation. Without one, the confirmation step isn't available, and the system falls back to the heuristic and says so.

The LLM-as-judge comparison from the original plan is not in this version. The structural heuristic is the baseline a judge would have to beat, so that comparison is the next thing to build. There's also no dashboard yet; the metrics the dashboard would show (escalation rate, sampled faithfulness, cost per task, p95 latency) are the ones the benchmark already reports where it can.

## Roadmap

Next, I want an LLM-backed planner with recorded outputs, so counterfactual replay works on real model behaviour. After that, a set of fault types the signals weren't written for, to measure generalization honestly. Then the span-level LLM judge, calibrated against a small human-labelled sample with Cohen's kappa reported alongside accuracy.

## License

MIT. See [LICENSE](LICENSE).
