from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Research Engine
Author: Heeran Paul
License: MIT
--------------------------------------------

UAI §23 — Research workflow with evidence separation.

Pipeline: decompose → collect (sources the current environment can
actually reach) → label each item FACT / INFERENCE / HYPOTHESIS /
UNCERTAINTY → detect contradictions → synthesize with confidence.

Rules enforced here:

* Never present uncertain information as fact — every claim carries
  an explicit label and a source reference.
* Collections that reach no real sources are reported honestly
  (status ``unverified``), never padded with fabricated citations.
* This module orchestrates data collection through whatever source
  ability the runtime provides (web/search/research); reasoning over
  the collected material is done by the Brain/reasoner, not here.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

LABEL_FACT = "FACT"
LABEL_INFERENCE = "INFERENCE"
LABEL_HYPOTHESIS = "HYPOTHESIS"
LABEL_UNCERTAINTY = "UNCERTAINTY"
LABELS = (LABEL_FACT, LABEL_INFERENCE, LABEL_HYPOTHESIS, LABEL_UNCERTAINTY)

CONFIDENCE_ORDER = {LABEL_FACT: 0.9, LABEL_INFERENCE: 0.6,
                    LABEL_HYPOTHESIS: 0.35, LABEL_UNCERTAINTY: 0.1}


@dataclass
class Evidence:
    """One labeled research item with its source."""

    label: str
    content: str
    source: str
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "content": self.content,
                "source": self.source, "confidence": self.confidence}


@dataclass
class ResearchResult:
    topic: str
    subquestions: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    synthesis: str = ""
    contradictions: List[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "unverified"   # unverified | verified | failed
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "subquestions": list(self.subquestions),
            "evidence": [e.to_dict() for e in self.evidence],
            "synthesis": self.synthesis,
            "contradictions": list(self.contradictions),
            "confidence": round(self.confidence, 3),
            "status": self.status,
            "error": self.error,
        }


class ResearchEngine:
    """Orchestrates research flows over real, reachable sources."""

    def __init__(self, source_ability=None, brain=None):
        """``source_ability`` must expose ``execute(topic, ...)`` returning a
        dict with real ``sources`` (e.g. SearchAbility/WebAbility result
        envelope). Absent a source, research is reported honestly."""
        self.source = source_ability
        self.brain = brain

    # ------------------------------------------------------------------
    def decompose(self, topic: str) -> List[str]:
        """Split a topic into concrete subquestions (deterministic split)."""
        parts = [p.strip() for p in str(topic or "").split(";") if p.strip()]
        if len(parts) > 1:
            return parts
        return [f"What is known about {topic}?",
                f"What evidence supports claims about {topic}?",
                f"What is uncertain or disputed about {topic}?"]

    # ------------------------------------------------------------------
    def collect(self, topic: str, max_items: int = 8) -> List[Evidence]:
        """Gather raw source material through the real source ability."""
        if self.source is None:
            return []
        try:
            result = self.source.execute(topic)
        except Exception:
            return []
        items = result.get("sources") if isinstance(result, dict) else None
        evidence: List[Evidence] = []
        for item in (items or [])[:max_items]:
            if isinstance(item, dict):
                content = str(item.get("content") or item.get("text") or item.get("snippet") or "").strip()
                source = str(item.get("url") or item.get("source") or "unknown")
            else:
                content = str(item).strip()
                source = "unknown"
            if content:
                evidence.append(Evidence(label=LABEL_UNCERTAINTY, content=content, source=source))
        return evidence

    # ------------------------------------------------------------------
    @staticmethod
    def label(evidence: List[Evidence]) -> List[Evidence]:
        """Assign labels deterministically where the material allows.

        Content carrying an explicit marker (``[FACT]``, ``[INFERENCE]``...)
        is honored. Uncorroborated single-source material stays
        UNCERTAINTY unless the caller (reasoner) relabels it with
        justification. This function never upgrades a claim by guesswork.
        """
        for item in evidence:
            text = item.content
            upper = text.upper()
            matched = next((lab for lab in LABELS if f"[{lab}]" in upper), None)
            if matched:
                item.label = matched
            elif text.lower().startswith(("according to", "source:", "citation:")):
                item.label = LABEL_FACT
            elif any(h in text.lower() for h in ("maybe", "possibly", "appears", "likely", "suggests")):
                item.label = LABEL_HYPOTHESIS
            elif text.lower().startswith(("therefore", "thus", "this implies", "it follows")):
                item.label = LABEL_INFERENCE
            # else: stays UNCERTAINTY (safe default)
            item.confidence = CONFIDENCE_ORDER[item.label]
        return evidence

    # ------------------------------------------------------------------
    @staticmethod
    def detect_contradictions(evidence: List[Evidence]) -> List[str]:
        """Find pairs of FACT items with opposed polarity on the same subject."""
        contradictions: List[str] = []
        facts = [e for e in evidence if e.label == LABEL_FACT]
        negations = ("not ", "never ", "no ", "cannot ", "isn't", "wasn't", "doesn't")
        for i, a in enumerate(facts):
            for b in facts[i + 1:]:
                a_neg = any(n in a.content.lower() for n in negations)
                b_neg = any(n in b.content.lower() for n in negations)
                if a_neg != b_neg and _share_subject(a.content, b.content):
                    contradictions.append(
                        f"'{a.content[:90]}' (from {a.source}) contradicts "
                        f"'{b.content[:90]}' (from {b.source})")
        return contradictions

    # ------------------------------------------------------------------
    def run(self, topic: str) -> ResearchResult:
        """Full workflow. Honest statuses: no sources → ``unverified``."""
        try:
            subquestions = self.decompose(topic)
            evidence = self.label(self.collect(topic))
            if not evidence:
                return ResearchResult(
                    topic=topic, subquestions=subquestions, status="unverified",
                    error="no reachable research source; nothing verified",
                    synthesis="No source material could be retrieved in this environment.")
            contradictions = self.detect_contradictions(evidence)
            fact_count = sum(1 for e in evidence if e.label == LABEL_FACT)
            confidence = round(sum(e.confidence for e in evidence) / len(evidence), 3)
            synthesis = self._synthesize(topic, evidence, contradictions)
            return ResearchResult(
                topic=topic, subquestions=subquestions, evidence=evidence,
                synthesis=synthesis, contradictions=contradictions,
                confidence=confidence,
                status="verified" if fact_count >= 2 and not contradictions else "unverified",
            )
        except Exception as exc:                      # honest failure envelope
            return ResearchResult(topic=topic, status="failed",
                                  error=str(exc)[:300], synthesis="")

    # ------------------------------------------------------------------
    def _synthesize(self, topic: str, evidence: List[Evidence],
                    contradictions: List[str]) -> str:
        lines: List[str] = [f"Research summary for: {topic}", ""]
        by_label: Dict[str, List[Evidence]] = {}
        for e in evidence:
            by_label.setdefault(e.label, []).append(e)
        for label in LABELS:
            for e in by_label.get(label, [])[:4]:
                lines.append(f"- [{label}] {e.content[:200]} (source: {e.source})")
        if contradictions:
            lines.append("")
            lines.append("Contradictions detected:")
            lines.extend(f"- {c}" for c in contradictions[:3])
        lines.append("")
        lines.append("Note: labels reflect evidence strength; "
                     "UNCERTAINTY items are unverified and must not be presented as fact.")
        return "\n".join(lines)


def _share_subject(a: str, b: str) -> bool:
    """Cheap overlap heuristic: same content words, different polarity."""
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "to", "of", "in",
                 "it", "that", "this", "and", "not", "no", "never"}
    ta = {w for w in str(a).lower().split() if w.isalnum()} - stopwords
    tb = {w for w in str(b).lower().split() if w.isalnum()} - stopwords
    return len(ta & tb) >= 2
