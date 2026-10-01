from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Research Ability
Author: Heeran Paul
License: MIT
--------------------------------------------

UAI §23 — Labeled research workflow as a pipeline ability.

Runs the real ResearchEngine (decompose → collect → label →
contradictions → synthesize) over an attached source ability. The
source is whatever the runtime can actually reach (web/search
ability); with no source attached, or when the source yields
nothing, the result is honestly ``unverified`` with empty evidence —
never fabricated sources, never fake successful searches.

Envelope(liability): ``status`` is the *workflow* outcome
(``success`` = the workflow ran; ``failed`` = bad input or engine
error). Whether the material is *verified* is carried separately in
``verification_status`` + ``confidence`` + per-item labels, so
callers (and step_verifier) can judge honestly.
"""


from typing import Any, Dict, Optional

from abilities.base_ability import BaseAbility


class ResearchAbility(BaseAbility):

    def __init__(self, source_ability=None):

        super().__init__(
            "research",
            "Research and analysis",
            verification=("evidence labeled FACT/INFERENCE/HYPOTHESIS/UNCERTAINTY "
                          "with sources; unverified when no source reachable"),
            timeout_s=60,
            risk="LOW",
        )
        self._source = source_ability

    ##################################################

    def attach_source(self, source_ability) -> None:
        """Wire a real source (web/search ability) after construction."""
        self._source = source_ability

    ##################################################

    def validate_input(self, task, **kwargs):
        topic = task.get("topic", "") if isinstance(task, dict) else task
        if not str(topic or "").strip():
            return "research topic must be a non-empty string"
        return ""

    ##################################################

    def execute(
        self,
        task,
        context=None,
        **kwargs,
    ) -> Dict[str, Any]:

        from cognition.research import ResearchEngine

        topic = task.get("topic", "") if isinstance(task, dict) else task
        topic = str(topic or "").strip()
        if not topic:
            return {"status": "failed", "error": "empty research topic",
                    "topic": "", "sources": [], "evidence": [],
                    "verification_status": "unverified"}

        engine = ResearchEngine(source_ability=self._source)
        try:
            result = engine.run(topic)
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300],
                    "topic": topic, "sources": [], "evidence": [],
                    "verification_status": "failed"}

        data = result.to_dict()
        return {

            "status": "success",

            "topic": data["topic"],

            "sources": [e["source"] for e in data["evidence"]],

            "evidence": data["evidence"],

            "synthesis": data["synthesis"],

            "contradictions": data["contradictions"],

            "confidence": data["confidence"],

            "verification_status": data["status"],

            "subquestions": data["subquestions"],

            # ``error`` is None on the honest-success path (even when
            # unverified — that is signaled by ``verification_status``,
            # not by an error): AbilityManager coerces any truthy
            # ``error`` into status=failed, which would mislabel a
            # correctly executed but unverified workflow. The engine's
            # explanatory note is preserved inside ``synthesis``.
            "error": None,

        }
