"""The support agent.

Each decision and each tool call is an OpenTelemetry span. Every step also
records the steps it depended on, which is the data the diagnosis layer turns
into a causal graph. Interventions can override a step's output, and that is
how counterfactual replays are executed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from .faults import apply_decision_fault, apply_tool_fault, prompt_version_for
from .planner import BASELINE_PROMPT_VERSION, Action, Observation, decide
from .tools import TOOLS

SERVICE_NAME = "support-agent"
MODEL_NAME = "rule-based-planner-v1"
MAX_STEPS = 8


@dataclass(frozen=True)
class StepContext:
    question: str
    observations: tuple[Observation, ...]
    args: dict


Intervention = Callable[[Any, StepContext], Any]


@dataclass(frozen=True)
class RunResult:
    verdict: str
    trace_id: int


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class SupportAgent:
    def __init__(
        self,
        exporter: SpanExporter | None = None,
        prompt_version: str = BASELINE_PROMPT_VERSION,
        max_steps: int = MAX_STEPS,
    ):
        self.exporter = exporter if exporter is not None else InMemorySpanExporter()
        self.prompt_version = prompt_version
        self.max_steps = max_steps
        self.provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("support_agent")

    def run(
        self,
        question: str,
        fault: str = "none",
        interventions: Mapping[str, Intervention] | None = None,
        scenario_id: str = "adhoc",
    ) -> RunResult:
        interventions = dict(interventions or {})
        version = prompt_version_for(fault, self.prompt_version)
        observations: list[Observation] = []

        with self.tracer.start_as_current_span("support_agent.run") as root:
            root.set_attribute("agent.question", question)
            root.set_attribute("agent.scenario_id", scenario_id)
            trace_id = root.get_span_context().trace_id

            for index in range(self.max_steps):
                decision_key = f"{index}.decision"
                with self.tracer.start_as_current_span("agent.decision") as span:
                    action = decide(question, observations, version)
                    action = apply_decision_fault(fault, action)
                    if decision_key in interventions:
                        ctx = StepContext(question, tuple(observations), dict(action.args))
                        action = interventions[decision_key](action, ctx)
                    _record_decision(span, decision_key, index, observations, action, version, question)
                    if action.kind == "final":
                        span.set_attribute("agent.verdict", action.verdict)
                        return RunResult(verdict=action.verdict, trace_id=trace_id)

                tool_key = f"{index}.tool"
                with self.tracer.start_as_current_span("agent.tool") as span:
                    result = TOOLS[action.name](**action.args)
                    result = apply_tool_fault(fault, action.name, result)
                    if tool_key in interventions:
                        ctx = StepContext(question, tuple(observations), dict(action.args))
                        result = interventions[tool_key](result, ctx)
                    _record_tool(span, tool_key, index, decision_key, action, result)
                observations.append(Observation(tool_key, action.name, dict(action.args), result))

            return RunResult(verdict="escalated", trace_id=trace_id)


def _record_decision(span, key, index, observations, action, version, question) -> None:
    payload = action.to_dict()
    span.set_attribute("agent.step.key", key)
    span.set_attribute("agent.step.index", index)
    span.set_attribute("agent.step.kind", "decision")
    span.set_attribute("agent.depends_on", _dump([o.key for o in observations]))
    span.set_attribute("agent.decision.action", _dump(payload))
    span.set_attribute("prompt.version", version)
    span.set_attribute("gen_ai.system", "rule_based")
    span.set_attribute("gen_ai.request.model", MODEL_NAME)
    span.set_attribute(
        "gen_ai.usage.input_tokens",
        _estimate_tokens(question + _dump([o.result for o in observations])),
    )
    span.set_attribute("gen_ai.usage.output_tokens", _estimate_tokens(_dump(payload)))


def _record_tool(span, key, index, decision_key, action, result) -> None:
    span.set_attribute("agent.step.key", key)
    span.set_attribute("agent.step.index", index)
    span.set_attribute("agent.step.kind", "tool")
    span.set_attribute("agent.depends_on", _dump([decision_key]))
    span.set_attribute("tool.name", action.name)
    span.set_attribute("tool.args", _dump(action.args))
    span.set_attribute("tool.result", _dump(result))
