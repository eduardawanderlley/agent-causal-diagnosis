"""Run one request through the agent from the command line.

    python -m support_agent "Can I still return PED-1004?"
    python -m support_agent "Can I still return PED-1004?" --fault prompt_drift
"""

from __future__ import annotations

import argparse

from .agent import SupportAgent
from .faults import FAULTS
from .telemetry import otlp_exporter_from_env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--fault", choices=FAULTS, default="none")
    args = parser.parse_args()

    exporter = otlp_exporter_from_env()
    agent = SupportAgent(exporter=exporter)
    result = agent.run(args.question, fault=args.fault)

    print(f"verdict:  {result.verdict}")
    print(f"trace id: {result.trace_id:032x}")
    if exporter is None:
        for span in agent.exporter.get_finished_spans():
            key = span.attributes.get("agent.step.key")
            if key is not None:
                print(f"  {key:<14} {span.name:<16} {span.attributes.get('agent.decision.action', span.attributes.get('tool.name'))}")
    else:
        print("spans exported to OTLP endpoint")


if __name__ == "__main__":
    main()
