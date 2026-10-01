from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evidence Model
Author: Heeran Paul
License: MIT
--------------------------------------------

Evidence distinguishes DIRECT / INFERRED / ASSUMED / UNVERIFIED /
CONTRADICTED claims, grounds answers in retrieved sources, detects
conflicts between sources instead of silently merging them, and
scores freshness so stale content is not treated as current.

Ownership: KNOWLEDGE (provenance-adjacent). Consumed by retrieval,
context assembly, and evaluation.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from knowledge.provenance import Provenance, parse_timestamp

_NEGATION_RE = re.compile(
    r"\b(not|no |never|n't\b|cannot|can't|won't|isn't|aren't|wasn't|weren't|"
    r"doesn't|don't|didn't|fails|failed|false|incorrect|wrong|disabled|"
    r"deprecated|removed|unsupported)\b",
    re.IGNORECASE,
)


class EvidenceType(str, Enum):
    DIRECT = "direct"
    INFERRED = "inferred"
    ASSUMED = "assumed"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"


@dataclass
class Evidence:
    """One supporting (or contradicting) piece of evidence."""

    statement: str
    source: str = "unknown"
    chunk_id: str = ""
    document_id: str = ""
    confidence: float = 0.5
    kind: EvidenceType = EvidenceType.UNVERIFIED
    timestamp: str = ""
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "statement": self.statement,
            "source": self.source,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "confidence": round(float(self.confidence), 3),
            "kind": self.kind.value,
            "timestamp": self.timestamp,
            "verified": self.verified,
            "metadata": dict(self.metadata),
        }


@dataclass
class Conflict:
    """Two sources that disagree; both are preserved, never merged."""

    topic: str
    source_a: str
    source_b: str
    excerpt_a: str = ""
    excerpt_b: str = ""
    fresher_source: str = ""
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "source_a": self.source_a,
            "source_b": self.source_b,
            "excerpt_a": self.excerpt_a,
            "excerpt_b": self.excerpt_b,
            "fresher_source": self.fresher_source,
            "detail": self.detail,
        }


def evidence_from_retrieved(statement: str, item: Any, confidence: Optional[float] = None) -> Evidence:
    """Build DIRECT evidence from a RetrievedItem (or compatible mapping)."""
    if isinstance(item, dict):
        chunk_id = str(item.get("chunk_id", ""))
        text = str(item.get("text", ""))
        score = float(item.get("score", 0.5))
        prov = item.get("provenance") or {}
    else:
        chunk_id = str(getattr(item, "chunk_id", ""))
        text = str(getattr(item, "text", ""))
        score = float(getattr(item, "score", 0.5))
        prov_obj = getattr(item, "provenance", None)
        prov = prov_obj.as_dict() if prov_obj is not None else {}
    _ = text  # statement carries the claim; source text stays in metadata
    return Evidence(
        statement=statement,
        source=str(prov.get("source", "unknown")),
        chunk_id=chunk_id,
        document_id=str(prov.get("document_id", "")),
        confidence=round(float(confidence if confidence is not None else score), 3),
        kind=EvidenceType.DIRECT,
        timestamp=str(prov.get("indexed_at", "")),
        verified=False,
        metadata={"provenance": prov},
    )


def _negation_signature(text: str) -> bool:
    return bool(_NEGATION_RE.search(text or ""))


def detect_conflicts(items: Sequence[Any], topic: str = "") -> List[Conflict]:
    """Flag pairs of sources whose stances disagree.

    Heuristic (transparent, not semantic): two items from *different*
    sources where exactly one carries negation language are reported as
    a potential conflict with both excerpts preserved.
    """
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(
                {
                    "text": str(item.get("text", "")),
                    "source": str((item.get("provenance") or {}).get("source", "unknown")),
                    "indexed_at": str((item.get("provenance") or {}).get("indexed_at", "")),
                }
            )
        else:
            prov = getattr(item, "provenance", None)
            prov_d = prov.as_dict() if prov is not None else {}
            normalized.append(
                {
                    "text": str(getattr(item, "text", "")),
                    "source": str(prov_d.get("source", "unknown")),
                    "indexed_at": str(prov_d.get("indexed_at", "")),
                }
            )
    conflicts: List[Conflict] = []
    for i in range(len(normalized)):
        for j in range(i + 1, len(normalized)):
            a, b = normalized[i], normalized[j]
            if a["source"] == b["source"]:
                continue
            if _negation_signature(a["text"]) != _negation_signature(b["text"]):
                ta = parse_timestamp(a["indexed_at"])
                tb = parse_timestamp(b["indexed_at"])
                fresher = ""
                if ta is not None and tb is not None:
                    fresher = a["source"] if ta >= tb else b["source"]
                conflicts.append(
                    Conflict(
                        topic=topic or "retrieved sources disagree",
                        source_a=a["source"],
                        source_b=b["source"],
                        excerpt_a=a["text"][:200],
                        excerpt_b=b["text"][:200],
                        fresher_source=fresher,
                        detail="negation-signal mismatch between sources; both preserved",
                    )
                )
    return conflicts


def freshness_score(indexed_at: Any, ttl_seconds: float = 30 * 86400.0, now: Optional[datetime] = None) -> float:
    """1.0 when fresh, decaying linearly to 0.0 at TTL expiry."""
    parsed = parse_timestamp(indexed_at)
    if parsed is None or ttl_seconds <= 0:
        return 0.0
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    age = max(0.0, (ref - parsed).total_seconds())
    return max(0.0, min(1.0, 1.0 - age / ttl_seconds))


def ground_answer(statements: Sequence[str], items: Sequence[Any]) -> List[Dict[str, Any]]:
    """Attach each statement to its best supporting retrieved item.

    QUERY -> RETRIEVE -> EVIDENCE -> REASON -> RESPONSE: this is the
    EVIDENCE step. Statements with no supporting item are marked
    UNVERIFIED rather than fabricated.
    """
    grounded: List[Dict[str, Any]] = []
    pool = list(items)
    for statement in statements:
        tokens = set(_NEGATION_RE.sub(" ", statement.lower()).split())
        best, best_overlap = None, 0
        for item in pool:
            text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
            overlap = len(tokens.intersection(str(text).lower().split()))
            if overlap > best_overlap:
                best, best_overlap = item, overlap
        if best is None:
            grounded.append({"statement": statement, "evidence": Evidence(statement, kind=EvidenceType.UNVERIFIED).as_dict()})
        else:
            grounded.append({"statement": statement, "evidence": evidence_from_retrieved(statement, best).as_dict()})
    return grounded
