from __future__ import annotations
"""Test-time learning / mistake-driven adaptation (Phase 6U).

Observe -> attempt -> detect -> diagnose -> update -> revise -> retry
-> verify -> retain. Learns through working memory, experience,
skills, and task-state updates — never through model-weight,
code, policy, or permission modification during task execution.
"""

from cognition.adaptation.executor import AdaptiveExecutor
from cognition.adaptation.failures import (FAILURE_TYPES, FailureRecord,
                                           FailureType, classify_failure)

__all__ = ["AdaptiveExecutor", "FAILURE_TYPES", "FailureRecord",
           "FailureType", "classify_failure"]
