"""CI gate: block a change that breaks behaviour the reference configuration gets right.

    python scripts/regression_gate.py                       # reference config, must pass
    python scripts/regression_gate.py --prompt-version v2-drift   # should fail

Exit code 0 means the candidate is safe to merge; 1 means it reintroduces failures.
"""

from __future__ import annotations

import argparse
import sys

from support_agent.evaluation import run_gate
from support_agent.planner import BASELINE_PROMPT_VERSION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-version", default=BASELINE_PROMPT_VERSION)
    args = parser.parse_args()

    report = run_gate(args.prompt_version)
    print(f"candidate prompt version: {args.prompt_version}")
    print(f"regressions:              {len(report.regressions)}")
    for scenario_id in report.regressions[:20]:
        print(f"  - {scenario_id}")
    print(f"fault-free failures:      {len(report.clean_failures)}")
    for scenario_id in report.clean_failures[:20]:
        print(f"  - {scenario_id}")
    print("GATE:", "PASS" if report.passed else "FAIL")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
