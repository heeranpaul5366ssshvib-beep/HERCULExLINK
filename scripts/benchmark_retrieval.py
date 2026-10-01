"""Deterministic retrieval benchmark (Phase G).

Offline-safe: the hash provider always runs; the sentence-transformers
provider runs only when installed with cached weights, otherwise it is
reported as skipped (honest, never faked).

Usage:  python scripts/benchmark_retrieval.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge.datasets import (
    build_dataset_fixture,
    evaluate_weight_grid,
    load_retrieval_dataset,
    rank_docs,
    score_query,
)
from knowledge.hybrid_retrieval import HybridRetriever
from knowledge.knowledge_manager import KnowledgeManager
from models.embeddings.hash_provider import HashEmbeddingProvider
from system.observability.trace import Tracer, trace_embedding, trace_retrieval


def build_provider_set():
    providers = {"hash": HashEmbeddingProvider()}
    try:
        from models.embeddings.sentence_transformer_provider import SentenceTransformerEmbeddingProvider

        candidate = SentenceTransformerEmbeddingProvider()
        if candidate.available():
            providers["st"] = candidate
        else:
            print("st provider unavailable (weights missing) — skipping live leg")
    except Exception as exc:
        print(f"st provider unavailable ({exc}) — skipping live leg")
    return providers


def benchmark_provider(name, provider, dataset, tracer, correlation):
    manager = KnowledgeManager()
    t0 = time.perf_counter()
    retriever = build_dataset_fixture(
        manager,
        dataset,
        embed_fn=provider.as_embed_fn(),
        embed_batch_fn=provider.embed_batch,
        embed_model_id=provider.model_id,
    )
    ingest_ms = (time.perf_counter() - t0) * 1000.0
    trace_embedding(tracer, correlation, provider.model_id, provider.dimension, 1, ingest_ms, False, ["ingest"])

    single_ms, batch_ms, texts = 0.0, 0.0, [d["text"] for d in dataset["documents"]]
    t0 = time.perf_counter()
    provider.embed(texts[0])
    single_ms = (time.perf_counter() - t0) * 1000.0
    t0 = time.perf_counter()
    provider.embed_batch(texts)
    batch_ms = (time.perf_counter() - t0) * 1000.0

    query_rows = []
    for query in dataset["queries"]:
        t0 = time.perf_counter()
        items = retriever.retrieve(str(query["text"]), top_k=5)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        docs = rank_docs([i.as_dict() for i in items])
        metrics = score_query(docs, list(query["relevant_docs"]))
        trace_retrieval(tracer, correlation, items[0].strategy.value if items else "none", len(items), latency_ms, docs[:3])
        query_rows.append({"query": query["id"], "latency_ms": round(latency_ms, 3), "docs": docs, **metrics})
    mean = lambda k: round(sum(r[k] for r in query_rows) / len(query_rows), 4)
    return {
        "provider": name,
        "model_id": provider.model_id,
        "dimension": provider.dimension,
        "ingest_ms": round(ingest_ms, 3),
        "single_embed_ms": round(single_ms, 3),
        "batch_embed_ms": round(batch_ms, 3),
        "batch_throughput_per_s": round(len(texts) / (batch_ms / 1000.0), 2) if batch_ms else 0.0,
        "mean_precision_at_3": mean("precision_at_k"),
        "mean_recall": mean("recall"),
        "mean_mrr": mean("mrr"),
        "queries": query_rows,
    }


def main():
    dataset = load_retrieval_dataset()
    tracer = Tracer()
    correlation = "bench-phase-g"
    providers = build_provider_set()
    report = {"dataset": dataset["name"], "providers": {}, "weight_grid": {}}
    for name, provider in providers.items():
        print(f"--- provider: {name} ({provider.model_id}, dim {provider.dimension})")
        result = benchmark_provider(name, provider, dataset, tracer, correlation)
        report["providers"][name] = result
        print(f"ingest {result['ingest_ms']}ms single {result['single_embed_ms']}ms "
              f"batch {result['batch_embed_ms']}ms ({result['batch_throughput_per_s']}/s)")
        print(f"P@3 {result['mean_precision_at_3']} R {result['mean_recall']} MRR {result['mean_mrr']}")

    # Fusion-weight benchmark on the deterministic provider.
    hash_provider = providers["hash"]
    manager = KnowledgeManager()
    build_dataset_fixture(manager, dataset, embed_fn=hash_provider.as_embed_fn(), embed_model_id=hash_provider.model_id)

    def factory(kw, vw):
        return HybridRetriever(manager.index, manager.embeddings, embed_fn=hash_provider.as_embed_fn(),
                               keyword_weight=kw, vector_weight=vw)

    grid = evaluate_weight_grid(factory, dataset)
    report["weight_grid"] = grid
    for row in grid["rows"]:
        print(f"w=({row['keyword_weight']},{row['vector_weight']}) P@3={row['precision_at_k']} R={row['recall']} MRR={row['mrr']}")
    print(f"best weights: {grid['best']}")

    out = Path("data/benchmarks/phase_g_retrieval.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
