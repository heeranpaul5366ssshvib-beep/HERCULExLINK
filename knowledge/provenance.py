from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Knowledge Provenance
Author: Heeran Paul
License: MIT
--------------------------------------------

Provenance answers, for every indexed item:

* Where did this come from?      (source / origin)
* When was it indexed?           (indexed_at, timezone-aware UTC)
* What document produced it?     (document_id / chunk_id / version)
* Which transformation made it?  (transformation chain)
* Retrieved or inferred?         (direct flag)

Ownership: KNOWLEDGE (reference material about the world).
Distinct from MEMORY (authorized interaction state) and
EXPERIENCE (validated task outcomes, see cognition/experience).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    """Timezone-aware UTC timestamp for new provenance records."""
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp, tolerating legacy naive strings.

    Legacy records indexed before the Phase E UTC migration carry naive
    UTC timestamp strings. They are interpreted as UTC
    rather than rejected, so old persisted data never raises::

        TypeError: can't compare offset-naive and offset-aware datetimes
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


@dataclass
class Provenance:
    """Provenance record attached to every indexed knowledge chunk."""

    source: str = "unknown"
    origin: str = "ingestion"
    document_id: str = ""
    chunk_id: str = ""
    content_type: str = "text/plain"
    version: str = "1"
    indexed_at: str = field(default_factory=utc_now_iso)
    transformation: List[str] = field(default_factory=list)
    direct: bool = True  # False when inferred/derived rather than retrieved
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "origin": self.origin,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "content_type": self.content_type,
            "version": self.version,
            "indexed_at": self.indexed_at,
            "transformation": list(self.transformation),
            "direct": self.direct,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Provenance":
        return cls(
            source=str(data.get("source", "unknown")),
            origin=str(data.get("origin", "ingestion")),
            document_id=str(data.get("document_id", "")),
            chunk_id=str(data.get("chunk_id", "")),
            content_type=str(data.get("content_type", "text/plain")),
            version=str(data.get("version", "1")),
            indexed_at=str(data.get("indexed_at") or utc_now_iso()),
            transformation=list(data.get("transformation") or []),
            direct=bool(data.get("direct", True)),
            metadata=dict(data.get("metadata") or {}),
        )

    def age_seconds(self, now: Optional[datetime] = None) -> float:
        """Age of the record in seconds; -1.0 when unparseable."""
        indexed = parse_timestamp(self.indexed_at)
        if indexed is None:
            return -1.0
        ref = now or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        return max(0.0, (ref - indexed).total_seconds())
