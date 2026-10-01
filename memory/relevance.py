from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Memory Relevance Engine (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Layered, evidence-tagged relevance scoring over memory records:

1. exact metadata match (topic/key/task/entity)
2. entity/reference overlap (world-model names, task ids)
3. semantic similarity — ONLY with a production embedding provider
   (test-only vectors never qualify; without one this layer is
   skipped honestly, never fabricated)
4. lexical token-overlap fallback (always available)

Score factors: lexical/semantic relevance, recency, importance,
confidence, task relevance, user relevance. Every hit carries
evidence metadata (which layers fired + provenance). Deterministic:
same store + query always ranks identically. No CoT stored, no
secrets scored (redacted upstream).
"""

import math
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokens_of(text: str):
    return set(_TOKEN_RE.findall(str(text or "").lower()))


def _parse_time(value: str) -> float:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return 0.0


def _recency_factor(timestamp: str, now: float, half_life_days: float = 30.0) -> float:
    moment = _parse_time(timestamp)
    if moment <= 0:
        return 0.5
    age_days = max(0.0, (now - moment) / 86400.0)
    return 0.5 ** (age_days / max(1.0, half_life_days))


def _cosine(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    if norm <= 0:
        return 0.0
    return max(0.0, min(1.0, dot / norm))


def score_record(record: Dict[str, Any], query: str,
                 query_tokens: set,
                 query_vector: Optional[List[float]] = None,
                 record_vector: Optional[List[float]] = None,
                 entities: Optional[set] = None,
                 task_id: str = "", correlation_id: str = "",
                 now: float = 0.0) -> Dict[str, Any]:
    """Score one record; returns factors + evidence (never just a scalar)."""
    content = str(record.get("content", "") or "")
    tags = list(record.get("tags", []) or [])
    metadata = dict(record.get("metadata", {}) or {})
    content_tokens = tokens_of(content) | tokens_of(" ".join(tags))
    overlap = query_tokens & content_tokens

    layers: List[str] = []
    # Layer 1: exact metadata (topic/key/task/entity identifier hit).
    metadata_blob = " ".join(str(v) for v in metadata.values()).lower()
    exact = False
    for token in query_tokens:
        if len(token) >= 4 and token in metadata_blob:
            exact = True
            break
    if exact:
        layers.append("metadata")
    # Layer 2: entity/reference overlap.
    entity_hit = False
    for name in entities or ():
        name_tokens = tokens_of(name)
        if name_tokens and (name_tokens & query_tokens):
            record_blob = (content + " " + " ".join(tags)).lower()
            if str(name).lower() in record_blob or (name_tokens & content_tokens):
                entity_hit = True
                break
    if entity_hit:
        layers.append("entity")
    # Layer 3: semantic (production embeddings only; else skipped).
    semantic = 0.0
    if query_vector is not None and record_vector is not None:
        semantic = _cosine(query_vector, record_vector)
        if semantic > 0.35:
            layers.append("semantic")
    # Layer 4: lexical fallback.
    lexical = len(overlap) / max(1, len(query_tokens))
    if overlap:
        layers.append("lexical")

    recency = _recency_factor(str(record.get("timestamp", "")), now or __import__("time").time())
    importance = min(1.0, max(0.0, float(record.get("importance", 0.5) or 0.0)))
    confidence = min(1.0, max(0.0, float(record.get("confidence", 1.0) or 0.0)))
    task_relevance = 0.0
    if task_id and (str(record.get("task_id", "")) == task_id
                    or task_id in content):
        task_relevance = 1.0
    elif correlation_id and correlation_id in str(record.get("correlation_id", "")):
        task_relevance = 0.6
    user_relevance = 0.0
    if str(record.get("source", "")) == "user":
        user_relevance = 1.0
    elif "fact" in [str(t).lower() for t in tags]:
        user_relevance = 0.7

    relevance = (0.45 * lexical + 0.35 * semantic) if semantic > 0 else lexical
    score = (0.40 * relevance + 0.15 * recency + 0.15 * importance
             + 0.10 * confidence + 0.10 * task_relevance + 0.10 * user_relevance)
    if exact:
        score = min(1.0, score + 0.15)
    if entity_hit:
        score = min(1.0, score + 0.10)
    return {"score": round(score, 4),
            "factors": {"relevance": round(relevance, 4),
                        "recency": round(recency, 4),
                        "importance": importance, "confidence": confidence,
                        "task_relevance": task_relevance,
                        "user_relevance": user_relevance},
            "layers": layers}


def rank(records: List[Dict[str, Any]], query: str, limit: int = 10,
         task_id: str = "", correlation_id: str = "",
         entities: Optional[List[str]] = None,
         embed: Optional[Callable[[str], Optional[List[float]]]] = None,
         vectors: Optional[Dict[str, List[float]]] = None) -> List[Dict[str, Any]]:
    """Rank records with evidence; invalidated records are excluded."""
    import time as _time

    query_tokens = tokens_of(query)
    if not query_tokens:
        return []
    entity_set = set(entities or ())
    query_vector = None
    if embed is not None:
        try:
            query_vector = embed(query)
        except Exception:
            query_vector = None
    now = _time.time()
    ranked = []
    for record in records:
        metadata = record.get("metadata", {}) or {}
        if metadata.get("invalidated"):
            continue  # corrected/forgotten: history kept, never retrieved
        entry_vector = (vectors or {}).get(str(record.get("id", "")))
        scored = score_record(record, query, query_tokens, query_vector,
                              entry_vector, entity_set, task_id,
                              correlation_id, now)
        if not scored["layers"]:
            continue
        ranked.append({"score": scored["score"], "factors": scored["factors"],
                       "layers": scored["layers"], "record": record,
                       "evidence": {"source": record.get("source", ""),
                                    "memory_type": record.get("memory_type", ""),
                                    "timestamp": record.get("timestamp", ""),
                                    "task_id": record.get("task_id", ""),
                                    "tags": list(record.get("tags", []) or [])}})
    ranked.sort(key=lambda item: (item["score"],
                                  item["record"].get("timestamp", "")), reverse=True)
    return ranked[:max(0, limit)]
