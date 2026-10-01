from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Persistent Memory Store
Author: Heeran Paul
License: MIT
--------------------------------------------

Single JSON-backed record store for durable memory (facts, episodic
summaries, experiences, procedures). Atomic writes (tmp + replace),
graceful recovery from corrupt files (backup + start empty), dedup by
content fingerprint, per-type retention caps, importance scoring.

Only concise summaries are stored — never private reasoning traces or
hidden chain-of-thought. Embeddings/vector search stay optional: the
built-in retrieval is deterministic token overlap.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("HERCULE.Memory.Store")

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Retention caps per memory type (Phase 8: bounded growth).
RETENTION_CAPS = {
    "semantic": 500,
    "episodic": 300,
    "experience": 300,
    "procedural": 200,
    "working": 50,
}

MAX_CONTENT_CHARS = 2000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def tokens_of(text: str) -> set:
    return set(_TOKEN_RE.findall(str(text or "").lower()))


def fingerprint(memory_type: str, content: str, task_id: str = "") -> str:
    normalized = re.sub(r"\s+", " ", str(content or "").strip().lower())
    raw = f"{memory_type}\x00{normalized}\x00{task_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class MemoryRecord:
    """Structured memory record (Phase 4 contract)."""

    id: str = ""
    memory_type: str = "episodic"  # semantic|episodic|experience|procedural|working
    timestamp: str = field(default_factory=_utc_now_iso)
    source: str = ""  # user|task|system
    content: str = ""  # concise summary only, never chain-of-thought
    context: Dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5  # 0.0..1.0
    confidence: float = 1.0  # 0.0..1.0
    tags: List[str] = field(default_factory=list)
    task_id: str = ""
    correlation_id: str = ""
    outcome: str = ""  # SUCCESS|PARTIAL|FAILED|RECOVERED|UNRECOVERED|""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in dict(data or {}).items() if k in known}
        record = cls()
        for key, value in clean.items():
            try:
                setattr(record, key, value)
            except Exception:
                pass
        return record


class PersistentStore:
    """JSON-file record store with atomic writes and corrupt recovery."""

    def __init__(self, path: str | Path, retention_caps: Optional[Dict[str, int]] = None):
        self.path = Path(path)
        self.retention_caps = dict(retention_caps or RETENTION_CAPS)
        self._records: Dict[str, MemoryRecord] = {}
        self._fingerprints: Dict[str, str] = {}  # fingerprint -> record id
        self._seq = 0
        self.load()

    # --------------------------------------------------
    def load(self) -> int:
        """Load from disk; corrupt files are backed up, never fatal."""
        self._records.clear()
        self._fingerprints.clear()
        if not self.path.exists():
            return 0
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            backup = self.path.with_suffix(f".corrupt-{datetime.now(timezone.utc):%Y%m%d%H%M%S}.bak")
            try:
                self.path.replace(backup)
            except Exception:
                pass
            logger.warning("memory store corrupt (%s); backed up, starting empty", exc)
            return 0
        items = data.get("records", []) if isinstance(data, dict) else []
        loaded = 0
        for item in items:
            try:
                record = MemoryRecord.from_dict(item)
                if not record.id:
                    continue
                self._records[record.id] = record
                self._fingerprints[fingerprint(
                    record.memory_type, record.content, record.task_id)] = record.id
                loaded += 1
            except Exception:
                continue  # skip corrupt records, keep the rest
        try:
            self._seq = max((int(r.id.split("-")[-1]) for r in self._records.values()
                             if "-" in r.id and r.id.split("-")[-1].isdigit()), default=0)
        except Exception:
            self._seq = len(self._records)
        return loaded

    def save(self) -> bool:
        """Atomic persist (tmp file + replace)."""
        from system.state_guard import check_state_write

        check_state_write(str(self.path), owner="memory")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1, "records": [r.as_dict() for r in self._records.values()]}
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=1)
                Path(tmp).replace(self.path)
            except Exception:
                try:
                    Path(tmp).unlink(missing_ok=True)
                except Exception:
                    pass
                raise
            return True
        except Exception as exc:
            logger.error("memory store save failed: %s", exc)
            return False

    # --------------------------------------------------
    def put(self, record: MemoryRecord) -> MemoryRecord:
        """Create or update (dedup by fingerprint: refresh, don't duplicate)."""
        record.content = str(record.content or "")[:MAX_CONTENT_CHARS]
        record.importance = min(1.0, max(0.0, float(record.importance or 0.0)))
        key = fingerprint(record.memory_type, record.content, record.task_id)
        existing_id = self._fingerprints.get(key)
        if existing_id and existing_id in self._records:
            existing = self._records[existing_id]
            existing.timestamp = record.timestamp or existing.timestamp
            existing.importance = max(existing.importance, record.importance)
            existing.tags = sorted(set(existing.tags) | set(record.tags or []))
            existing.metadata.update(record.metadata or {})
            if record.outcome:
                existing.outcome = record.outcome
            return existing
        self._seq += 1
        if not record.id:
            record.id = f"mem-{self._seq}"
        self._records[record.id] = record
        self._fingerprints[key] = record.id
        self._enforce_retention(record.memory_type)
        return record

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        return self._records.get(record_id)

    def delete(self, record_id: str) -> bool:
        record = self._records.pop(record_id, None)
        if record is None:
            return False
        key = fingerprint(record.memory_type, record.content, record.task_id)
        self._fingerprints.pop(key, None)
        return True

    def all(self, memory_type: str = "") -> List[MemoryRecord]:
        items = list(self._records.values())
        if memory_type:
            items = [r for r in items if r.memory_type == memory_type]
        return items

    def search(self, query: str, memory_type: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """Deterministic token-overlap retrieval (no embeddings required)."""
        query_tokens = tokens_of(query)
        if not query_tokens:
            return []
        scored = []
        for record in self.all(memory_type):
            if (record.metadata or {}).get("invalidated"):
                continue  # corrected/forgotten: history kept, never retrieved
            haystack = tokens_of(record.content) | tokens_of(" ".join(record.tags))
            overlap = query_tokens & haystack
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query_tokens)) * 0.7 + record.importance * 0.3
            scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1].timestamp), reverse=True)
        return [{"score": round(score, 3), "record": record.as_dict()}
                for score, record in scored[: max(0, limit)]]

    # --------------------------------------------------
    def _enforce_retention(self, memory_type: str) -> None:
        cap = int(self.retention_caps.get(memory_type, 200))
        group = [r for r in self._records.values() if r.memory_type == memory_type]
        if len(group) <= cap:
            return
        # Explicit user memories are never evicted merely for age/size;
        # only non-explicit records compete for retention.
        evictable = [r for r in group
                     if not (r.source == "user" and "fact" in [str(t).lower() for t in (r.tags or [])])]
        protected = len(group) - len(evictable)
        allowance = max(0, cap - protected)
        if len(evictable) <= allowance:
            return
        # Evict lowest (importance, timestamp) first.
        evictable.sort(key=lambda r: (r.importance, r.timestamp))
        for victim in evictable[: len(evictable) - allowance]:
            self.delete(victim.id)

    def statistics(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for record in self._records.values():
            by_type[record.memory_type] = by_type.get(record.memory_type, 0) + 1
        return {"total": len(self._records), "by_type": by_type, "path": str(self.path)}
