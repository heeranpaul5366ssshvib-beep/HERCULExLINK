from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Retrieval Benchmark Datasets
Author: Heeran Paul
License: MIT
--------------------------------------------

Deterministic dataset loading + fixture construction + doc-level
scoring for retrieval benchmarks. Judgments are document ids (robust
to chunking); chunk->document mapping comes from stored provenance.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DATASET_DIR = Path(__file__).resolve().parent / "datasets"


def load_retrieval_dataset(name: str = "phase_g_retrieval") -> Dict[str, Any]:
    path = DATASET_DIR / f"{name}.json"
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def doc_of_chunk(chunk_id: str, provenance: Optional[Dict[str, Any]] = None) -> str:
    if provenance and provenance.get("document_id"):
        return str(provenance["document_id"])
    return str(chunk_id).split("#c")[0]


def build_dataset_fixture(
    knowledge_manager,
    dataset: Dict[str, Any],
    embed_fn: Optional[Callable] = None,
    embed_batch_fn: Optional[Callable] = None,
    embed_model_id: str = "benchmark-fixture",
    vector_store=None,
):
    """Ingest every dataset document; backdate ``age_days`` provenance."""
    from knowledge.hybrid_retrieval import HybridRetriever

    chunk_size = int(dataset.get("chunk_size", 30))
    overlap = int(dataset.get("overlap", 5))
    for doc in dataset.get("documents", []):
        knowledge_manager.ingest_document(
            doc["document_id"],
            doc["text"],
            source=doc.get("source", "benchmark"),
            version=str(doc.get("version", "1")),
            metadata={"benchmark": dataset.get("name", "")},
            embed_fn=embed_fn,
            embed_batch_fn=embed_batch_fn,
            embed_model_id=embed_model_id,
            vector_store=vector_store,
            chunk_size=chunk_size,
            overlap=overlap,
        )
    # Backdate provenance for freshness scenarios (in-place record edit).
    now = datetime.now(timezone.utc)
    for doc in dataset.get("documents", []):
        age_days = doc.get("age_days")
        if not age_days:
            continue
        stamped = (now - timedelta(days=float(age_days))).isoformat()
        prefix = doc["document_id"] + "#c"
        for chunk_id, record in list(knowledge_manager.embeddings.all().items()):
            if str(chunk_id).startswith(prefix):
                meta = (record or {}).get("metadata") or {}
                prov = meta.get("provenance") or {}
                prov["indexed_at"] = stamped
    return HybridRetriever(
        knowledge_manager.index,
        knowledge_manager.embeddings,
        vector_store=vector_store,
        embed_fn=embed_fn,
    )


def rank_docs(items: List[Dict[str, Any]]) -> List[str]:
    """Deduplicated document ids in chunk-rank order."""
    ordered: List[str] = []
    for item in items:
        doc = doc_of_chunk(str(item.get("chunk_id", "")), item.get("provenance") or {})
        if doc not in ordered:
            ordered.append(doc)
    return ordered


def score_query(ranked_docs: List[str], relevant_docs: List[str], k: int = 3) -> Dict[str, float]:
    relevant = set(relevant_docs)
    top = ranked_docs[:k]
    hits = sum(1 for doc in top if doc in relevant)
    precision = hits / len(top) if top else 0.0
    recall = sum(1 for doc in relevant if doc in ranked_docs) / len(relevant) if relevant else 0.0
    reciprocal = 0.0
    for rank, doc in enumerate(ranked_docs, start=1):
        if doc in relevant:
            reciprocal = 1.0 / rank
            break
    return {"precision_at_k": precision, "recall": recall, "mrr": reciprocal}


def evaluate_weight_grid(
    make_retriever: Callable[[float, float], Any],
    dataset: Dict[str, Any],
    grid: Optional[List[tuple]] = None,
    k: int = 3,
) -> Dict[str, Any]:
    """Benchmark lexical/semantic fusion weights on fixed data."""
    grid = grid or [(1.0, 0.0), (0.6, 0.4), (0.4, 0.6), (0.2, 0.8), (0.0, 1.0)]
    rows: List[Dict[str, Any]] = []
    for keyword_weight, vector_weight in grid:
        retriever = make_retriever(keyword_weight, vector_weight)
        scores = []
        for query in dataset.get("queries", []):
            items = retriever.retrieve(str(query["text"]), top_k=5)
            docs = rank_docs([i.as_dict() if hasattr(i, "as_dict") else dict(i) for i in items])
            scores.append(score_query(docs, list(query["relevant_docs"]), k))
        mean = {
            key: round(sum(s[key] for s in scores) / len(scores), 4) if scores else 0.0
            for key in ("precision_at_k", "recall", "mrr")
        }
        rows.append({"keyword_weight": keyword_weight, "vector_weight": vector_weight, **mean})
    best = max(rows, key=lambda r: (r["mrr"], r["precision_at_k"], r["recall"]))
    return {"rows": rows, "best": best}
