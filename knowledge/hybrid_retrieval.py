from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Hybrid Retrieval Engine 2.0
Author: Heeran Paul
License: MIT
--------------------------------------------

QUERY -> QUERY ANALYSIS -> NORMALIZATION -> STRATEGY SELECTION
  -> VECTOR / KEYWORD / METADATA RETRIEVAL -> FILTERING
  -> RANKING -> OPTIONAL RERANKING -> CONTEXT CONSTRUCTION

Vector similarity alone is not assumed sufficient: exact-term
queries use the keyword index, metadata-filtered queries constrain
by provenance fields, freshness-aware queries boost recency, and
complex queries fuse lexical + semantic signals.

Ownership: KNOWLEDGE. Wraps the existing ``IndexManager`` and
``EmbeddingIndex`` (plus an optional ``VectorMemory`` search backend)
without replacing them.
"""

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from knowledge.ingestion import hash_embed
from knowledge.provenance import Provenance, parse_timestamp

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_FILTER_RE = re.compile(r"(\w+):([^\s]+)")

_FRESHNESS_WORDS = {"latest", "recent", "newest", "updated", "current", "fresh"}
_HISTORY_WORDS = {"previous", "previously", "before", "earlier", "last", "history", "attempted", "past"}
_COMPLEX_WORDS = {"compare", "versus", "vs", "difference", "differences", "research", "overview", "survey", "pros", "cons"}


class RetrievalStrategy(str, Enum):
    EXACT_TERM = "exact_term"
    SEMANTIC = "semantic"
    METADATA_FILTER = "metadata_filter"
    HYBRID = "hybrid"
    FRESHNESS_AWARE = "freshness_aware"
    TASK_HISTORY = "task_history"


@dataclass
class QueryAnalysis:
    normalized: str
    tokens: List[str]
    filters: Dict[str, str]
    strategy: RetrievalStrategy
    reasons: List[str] = field(default_factory=list)


def analyze_query(query: str) -> QueryAnalysis:
    """Classify a query into a retrieval strategy (deterministic rules)."""
    raw = (query or "").strip()
    normalized = raw.lower()
    filters = dict(_FILTER_RE.findall(normalized))
    tokens = _TOKEN_RE.findall(normalized)
    reasons: List[str] = []

    quoted = len(raw) >= 2 and raw.startswith('"') and raw.endswith('"')
    if filters:
        reasons.append(f"metadata filters: {sorted(filters)}")
        return QueryAnalysis(normalized, tokens, filters, RetrievalStrategy.METADATA_FILTER, reasons)
    if quoted or (len(tokens) == 1 and tokens):
        reasons.append("single/quoted term -> lexical lookup")
        return QueryAnalysis(normalized, tokens, filters, RetrievalStrategy.EXACT_TERM, reasons)
    if _FRESHNESS_WORDS.intersection(tokens):
        reasons.append("recency signal words present")
        return QueryAnalysis(normalized, tokens, filters, RetrievalStrategy.FRESHNESS_AWARE, reasons)
    if _HISTORY_WORDS.intersection(tokens):
        reasons.append("task-history signal words present")
        return QueryAnalysis(normalized, tokens, filters, RetrievalStrategy.TASK_HISTORY, reasons)
    if _COMPLEX_WORDS.intersection(tokens) or len(tokens) >= 8:
        reasons.append("complex/multi-aspect query -> hybrid fusion")
        return QueryAnalysis(normalized, tokens, filters, RetrievalStrategy.HYBRID, reasons)
    reasons.append("default conceptual query -> semantic retrieval")
    return QueryAnalysis(normalized, tokens, filters, RetrievalStrategy.SEMANTIC, reasons)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    m = min(len(a), len(b))
    if m == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a[:m], b[:m]))
    na = math.sqrt(sum(x * x for x in a[:m])) or 1.0
    nb = math.sqrt(sum(y * y for y in b[:m])) or 1.0
    return max(0.0, min(1.0, dot / (na * nb)))


@dataclass
class RetrievedItem:
    chunk_id: str
    text: str
    score: float
    strategy: RetrievalStrategy
    rank: int = 0
    provenance: Optional[Provenance] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "score": round(self.score, 4),
            "strategy": self.strategy.value,
            "rank": self.rank,
            "provenance": self.provenance.as_dict() if self.provenance else {},
            "metadata": dict(self.metadata),
        }


@dataclass
class RetrievalQuality:
    """Measured retrieval quality for one query execution."""

    strategy: str
    latency_ms: float
    result_count: int
    candidates_evaluated: int
    duplicate_rate: float
    score_spread: float

    def precision_at_k(self, relevant_ids: Sequence[str], k: int, ranked_ids: Sequence[str]) -> float:
        if k <= 0:
            return 0.0
        top = list(ranked_ids)[:k]
        hits = sum(1 for cid in top if cid in set(relevant_ids))
        return hits / len(top) if top else 0.0

    def recall(self, relevant_ids: Sequence[str], ranked_ids: Sequence[str]) -> float:
        if not relevant_ids:
            return 0.0
        found = sum(1 for cid in set(relevant_ids) if cid in set(ranked_ids))
        return found / len(relevant_ids)

    @staticmethod
    def mrr(ranked_ids: Sequence[str], relevant_ids: Sequence[str]) -> float:
        """Mean reciprocal rank of the first relevant hit (0.0 when none)."""
        wanted = set(relevant_ids)
        for rank, cid in enumerate(ranked_ids, start=1):
            if cid in wanted:
                return 1.0 / rank
        return 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "latency_ms": round(self.latency_ms, 3),
            "result_count": self.result_count,
            "candidates_evaluated": self.candidates_evaluated,
            "duplicate_rate": round(self.duplicate_rate, 4),
            "score_spread": round(self.score_spread, 4),
        }


class HybridRetriever:
    """Strategy-aware retrieval over an IndexManager + EmbeddingIndex."""

    def __init__(
        self,
        index=None,
        embeddings=None,
        vector_store=None,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6,
    ):
        self.index = index
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.embed_fn = embed_fn or hash_embed
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.last_quality: Optional[RetrievalQuality] = None

    # --------------------------------------------------
    # lexical path
    # --------------------------------------------------
    def _keyword_scores(self, tokens: List[str]) -> Dict[str, float]:
        if self.index is None or not tokens:
            return {}
        hits: Dict[str, int] = {}
        for token in set(tokens):
            try:
                for doc_id in self.index.search(token) or []:
                    hits[doc_id] = hits.get(doc_id, 0) + 1
            except Exception:
                continue
        denom = max(1, len(set(tokens)))
        return {doc_id: count / denom for doc_id, count in hits.items()}

    # --------------------------------------------------
    # semantic path
    # --------------------------------------------------
    def _all_vectors(self) -> Dict[str, Dict[str, Any]]:
        if self.embeddings is None:
            return {}
        try:
            return dict(self.embeddings.all() or {})
        except Exception:
            return {}

    def _vector_scores(self, query: str, top_k: int) -> Dict[str, float]:
        try:
            query_vector = self.embed_fn(query)
        except Exception:
            return {}
        if not isinstance(query_vector, (list, tuple)) or not query_vector:
            return {}
        store = self.vector_store
        store_dim = getattr(store, "dim", 0) if store is not None else 0
        if store_dim and len(query_vector) != store_dim:
            raise ValueError(
                f"EMBEDDING_DIMENSION_MISMATCH: query dim {len(query_vector)}, vector store dim {store_dim}"
            )
        # Prefer the optimized VectorMemory backend when it has data.
        if store is not None:
            try:
                results = store.search(query_vector, top_k=top_k) or []
                if results:
                    out: Dict[str, float] = {}
                    for entry in results:
                        meta = entry.get("metadata") or {}
                        cid = str(meta.get("chunk_id") or meta.get("document_id") or entry.get("text", "")[:64])
                        out[cid] = float(entry.get("score", 0.0))
                    return out
            except ValueError:
                raise
            except Exception:
                pass
        vectors = self._all_vectors()
        if vectors:
            stored_dims = {len((record or {}).get("embedding") or []) for record in vectors.values()}
            stored_dims.discard(0)
            if stored_dims and len(query_vector) not in stored_dims:
                raise ValueError(
                    f"EMBEDDING_DIMENSION_MISMATCH: query dim {len(query_vector)}, index dims {sorted(stored_dims)}"
                )
        scores: Dict[str, float] = {}
        for chunk_id, record in vectors.items():
            vector = (record or {}).get("embedding") or []
            if vector:
                scores[chunk_id] = _cosine(query_vector, vector)
        return scores

    # --------------------------------------------------
    # metadata path
    # --------------------------------------------------
    def _record_text(self, chunk_id: str) -> str:
        record = self._all_vectors().get(chunk_id) or {}
        meta = record.get("metadata") or {}
        text = str(meta.get("text") or "")
        return text

    def _record_provenance(self, chunk_id: str) -> Optional[Provenance]:
        record = self._all_vectors().get(chunk_id) or {}
        meta = record.get("metadata") or {}
        prov = meta.get("provenance")
        if isinstance(prov, dict):
            try:
                return Provenance.from_dict(prov)
            except Exception:
                return None
        return None

    def _matches_filters(self, chunk_id: str, filters: Dict[str, str]) -> bool:
        if not filters:
            return True
        prov = self._record_provenance(chunk_id)
        haystacks = {
            "source": (prov.source if prov else "").lower(),
            "type": (prov.content_type if prov else "").lower(),
            "content_type": (prov.content_type if prov else "").lower(),
            "document": (prov.document_id if prov else chunk_id).lower(),
            "document_id": (prov.document_id if prov else chunk_id).lower(),
            "version": (prov.version if prov else "").lower(),
        }
        for key, wanted in filters.items():
            actual = haystacks.get(key.lower())
            if actual is None or wanted.lower() not in actual:
                return False
        return True

    # --------------------------------------------------
    # fusion + ranking
    # --------------------------------------------------
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        strategy: Optional[RetrievalStrategy] = None,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[RetrievedItem]:
        started = time.perf_counter()
        analysis = analyze_query(query)
        active = strategy or analysis.strategy
        query_filters = dict(filters or analysis.filters)

        keyword = self._keyword_scores(analysis.tokens)
        # Vector scoring is lazy: exact-term lookup never embeds, so a
        # corrupt/foreign-dimensional vector store cannot break lexical
        # retrieval. Strategies that need vectors raise dimension
        # mismatches explicitly instead of degrading silently.
        vector: Dict[str, float] = {}
        if active != RetrievalStrategy.EXACT_TERM:
            vector = self._vector_scores(analysis.normalized, top_k=max(top_k * 4, 10))

        if active == RetrievalStrategy.EXACT_TERM:
            fused = {cid: s for cid, s in keyword.items()}
        elif active == RetrievalStrategy.SEMANTIC:
            fused = {cid: s for cid, s in vector.items()}
        elif active == RetrievalStrategy.METADATA_FILTER:
            universe = set(keyword) | set(vector) | set(self._all_vectors())
            fused = {
                cid: (self.keyword_weight * keyword.get(cid, 0.0) + self.vector_weight * vector.get(cid, 0.0))
                for cid in universe
                if self._matches_filters(cid, query_filters)
            }
        elif active in (RetrievalStrategy.FRESHNESS_AWARE, RetrievalStrategy.TASK_HISTORY):
            universe = set(keyword) | set(vector)
            now = datetime.now(timezone.utc)
            fused = {}
            for cid in universe:
                base = self.keyword_weight * keyword.get(cid, 0.0) + self.vector_weight * vector.get(cid, 0.0)
                prov = self._record_provenance(cid)
                boost = 0.0
                if prov is not None:
                    age_days = prov.age_seconds(now) / 86400.0
                    if age_days >= 0:
                        boost = 0.25 / (1.0 + age_days)
                fused[cid] = base + (boost if active == RetrievalStrategy.FRESHNESS_AWARE else 0.0)
        else:  # HYBRID
            universe = set(keyword) | set(vector)
            fused = {
                cid: self.keyword_weight * keyword.get(cid, 0.0) + self.vector_weight * vector.get(cid, 0.0)
                for cid in universe
            }

        # Deduplicate (keep max score), drop empties, rank.
        candidates = len(fused)
        duplicate_ids = set(keyword) & set(vector)
        duplicates = len([cid for cid in duplicate_ids if cid in fused])
        best: Dict[str, float] = {}
        for cid, score in fused.items():
            if score <= 0:
                continue
            if cid not in best or score > best[cid]:
                best[cid] = score
        ordered = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[: max(0, top_k)]

        items: List[RetrievedItem] = []
        for rank, (cid, score) in enumerate(ordered, start=1):
            prov = self._record_provenance(cid)
            meta = dict((self._all_vectors().get(cid) or {}).get("metadata") or {})
            items.append(
                RetrievedItem(
                    chunk_id=cid,
                    text=self._record_text(cid),
                    score=score,
                    strategy=active,
                    rank=rank,
                    provenance=prov,
                    metadata={k: v for k, v in meta.items() if k != "provenance"},
                )
            )

        spread = (ordered[0][1] - ordered[-1][1]) if len(ordered) > 1 else 0.0
        self.last_quality = RetrievalQuality(
            strategy=active.value,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            result_count=len(items),
            candidates_evaluated=candidates,
            duplicate_rate=(duplicates / candidates) if candidates else 0.0,
            score_spread=spread,
        )
        return items
