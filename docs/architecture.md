# Architecture

## Components

The system has two packages that are deliberately kept apart. `support_agent` produces traces. `causal_diagnosis` reads them. The diagnosis package has no import of the agent, so anything that writes the same span schema can be diagnosed with it.

`support_agent` contains four tools, a planner, a fault layer and an intervention registry. The planner takes the question and the observations so far and returns one action, either a tool call or a final verdict. The agent loop executes the action, records it as a span, and feeds the result back to the planner. Faults are applied between the planner and the tools, and between the tools and the loop. Interventions are applied last, which is what allows a fix to override a faulted step during replay.

`causal_diagnosis` builds a graph from one run's spans, scores steps, ranks them, and optionally confirms the top candidates through a replay callable supplied by the caller.

## Data flow

```
question
  │
  ▼
SupportAgent.run ──► agent.decision ──► agent.tool ──► agent.decision ──► … ──► final
        │                  │                 │
        │            span attributes:   span attributes:
        │            depends_on,        tool.name, tool.args,
        │            decision.action,   tool.result
        │            prompt.version
        ▼
OpenTelemetry SDK ──► OTLP ──► Collector ──► Langfuse
                                         └──► LangSmith

offline:  spans ──► TraceGraph ──► signals ──► ranking ──► replay ──► Diagnosis
```

## Span schema

Each run produces one root span, `support_agent.run`, and then a sequence of child spans. Each child carries a step key of the form `N.decision` or `N.tool`, where N is the step index. The keys are stable across replays of the same input, which is what lets an intervention address a specific step.

| Attribute | Present on | Meaning |
|---|---|---|
| `agent.question` | root | The user's message |
| `agent.scenario_id` | root | Identifier of the scenario, for joining with the benchmark |
| `agent.step.key` | decision, tool | Stable step key, for example `2.decision` |
| `agent.step.index` | decision, tool | Step index in the run |
| `agent.step.kind` | decision, tool | `decision` or `tool` |
| `agent.depends_on` | decision, tool | JSON list of the step keys this step consumed |
| `agent.decision.action` | decision | JSON with the chosen action: kind, tool name, arguments, verdict |
| `agent.verdict` | final decision | Final answer: `eligible`, `not_eligible` or `escalated` |
| `prompt.version` | decision | Prompt version in effect |
| `tool.name`, `tool.args`, `tool.result` | tool | What the tool was called with and what it returned |
| `gen_ai.system`, `gen_ai.request.model` | decision | Planner identity, in GenAI semantic-convention style |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | decision | Token estimates; the rule-based planner estimates them from text length |

The schema deliberately contains no fault information. The one exception is `agent.scenario_id`, whose label names the scenario for joining with the benchmark; the diagnosis never reads it. A test checks that no other attribute mentions a fault, so the diagnosis is measured on what an operator would actually see.

## Design decisions

The planner is rule-based. That is a trade-off I made on purpose. An LLM planner makes results non-deterministic, costs money on every benchmark run, and turns the ground truth into a moving target. The interface is the same one an LLM planner would implement, so swapping it in is a contained change.

Replay re-runs the agent from the start rather than from a checkpoint. For a deterministic agent that's exact and simple. For an LLM agent you would replay from the checkpoint with recorded model outputs, so that the only thing that changes is the step being corrected.

Diagnosis takes the replay as a callable rather than importing the agent. That keeps the causal logic testable on its own, and lets the same code run against a production replay mechanism.

The OpenTelemetry Collector sits between the agent and the two vendors. The application emits OTLP once and never changes when a vendor is added or removed, and the comparison between Langfuse and LangSmith is made on identical traces.
