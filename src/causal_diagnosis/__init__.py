"""Span-level causal diagnosis with counterfactual confirmation.

This package reads OpenTelemetry spans and knows nothing about the agent that
produced them. Plug in any replay function to enable counterfactual checks.
"""

from .graph import Step, TraceGraph
from .localize import Candidate, Diagnosis, baseline_rankings, diagnose

__all__ = ["Candidate", "Diagnosis", "Step", "TraceGraph", "baseline_rankings", "diagnose"]
