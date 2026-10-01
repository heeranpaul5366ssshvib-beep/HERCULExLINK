from __future__ import annotations
"""Deterministic moral-reasoning analyzer (Phase 8F/8H).

``analyze`` extracts stakeholders, actions, consequences, principles,
uncertainty, and tradeoffs from scenario text using explicit keyword
rules, then composes an explanation. It outputs a RECOMMENDATION ONLY;
``authorize`` always defers to an injected PolicyManager, and moral
reasoning can never widen permissions (attempts to do so are flagged).
"""

import re
from typing import Any, Dict, List

from cognition.moral_reasoning.frameworks import FRAMEWORKS, PRINCIPLE_CUES


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _stakeholders(text: str) -> List[str]:
    found = []
    for cand in ("user", "users", "operator", "public", "third part",
                 "minor", "employee", "customer", "patient", "driver",
                 "pedestrian", "passenger", "company", "community"):
        if cand in text.lower() and cand not in found:
            found.append(cand)
    return found or ["unspecified-party"]


def _actions(text: str) -> List[str]:
    acts = []
    for sent in _sentences(text):
        if re.search(r"\b(should|must|allow|permit|block|refuse|disclose|share|act)\b",
                     sent, re.I):
            acts.append(sent[:160])
    return acts[:4] or ["(no explicit action stated)"]


def _principles(text: str) -> List[str]:
    low = text.lower()
    hits = [name for name, cues in PRINCIPLE_CUES.items()
            if any(c in low for c in cues)]
    return hits or ["consequence"]


def analyze(scenario: str, options: List[str] | None = None) -> Dict[str, Any]:
    """Analyze a scenario. Returns explanation + uncertainty, no authorization."""
    text = str(scenario or "")
    principles = _principles(text)
    consequences = [s for s in _sentences(text)
                    if re.search(r"\b(if|then|will|would|lead|cause|result)\b", s, re.I)][:4]
    uncertain = ("uncertain" in text.lower() or "unknown" in text.lower()
                 or "maybe" in text.lower() or not consequences)
    tradeoff = len(principles) >= 2
    lines = [
        f"Stakeholders: {', '.join(_stakeholders(text))}.",
        f"Principles engaged: {', '.join(principles)}.",
    ]
    for name in principles:
        lines.append(f"- {name}: {FRAMEWORKS[name]}.")
    if tradeoff:
        lines.append(f"Tradeoff: {principles[0]} pulls against {principles[1]}; "
                     "neither automatically wins — stakes and consent decide.")
    lines.append("Uncertainty: " + ("factual gaps remain; decide conservatively."
                                    if uncertain else "facts as stated."))
    lines.append("This is analysis, not authorization: HERCULE Core policy decides.")
    return {"stakeholders": _stakeholders(text),
            "actions": _actions(text),
            "consequences": consequences,
            "principles": principles,
            "tradeoff": tradeoff,
            "uncertain": uncertain,
            "frameworks": {k: FRAMEWORKS[k] for k in principles},
            "explanation": " ".join(lines),
            "options": list(options or []),
            "authorization": "NOT-GRANTED (analyzer never authorizes)"}


def authorize(recommendation: str, action: Dict[str, Any],
              policy_manager) -> Dict[str, Any]:
    """Separate authorization: model recommends, Core disposes (§8H).

    Returns the policy verdict plus a flag if reasoning attempted to
    widen permissions (always denied here).
    """
    widening = bool(re.search(r"\b(grant|permit|bypass|override|escalate)\b",
                              str(recommendation), re.I))
    verdict = policy_manager.evaluate(str(action.get("tool", "UNKNOWN")),
                                      {"risk": action.get("risk", "LOW")})
    if widening:
        verdict = {**verdict, "allowed": False,
                   "reason": "moral reasoning cannot grant permissions"}
    return {"recommendation": str(recommendation)[:300],
            "attempted_widening": widening,
            "policy": verdict}
