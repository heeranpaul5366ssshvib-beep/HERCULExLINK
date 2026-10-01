"""Phase G: deterministic retrieval dataset, weight benchmark, live embeddings."""

import pytest

from knowledge.datasets import (
    build_dataset_fixture,
    doc_of_chunk,
    evaluate_weight_grid,
    load_retrieval_dataset,
    rank_docs,
    score_query,
)
from knowledge.evidence import detect_conflicts, ground_answer
from knowledge.hybrid_retrieval import HybridRetriever, RetrievalQuality, RetrievalStrategy
from knowledge.knowledge_manager import KnowledgeManager
from models.embeddings.hash_provider import HashEmbeddingProvider
from models.embeddings.sentence_transformer_provider import SentenceTransformerEmbeddingProvider


def test_dataset_has_full_coverage():
    dataset = load_retrieval_dataset()
    assert len(dataset["documents"]) >= 7
    kinds = {q["id"] for q in dataset["queries"]}
    assert {"exact-adapters", "semantic-router", "paraphrase-cache", "metadata-source",
            "fresh-ttl", "duplicate-checkpoint", "conflict-ttl", "history-router"} <= kinds
    for query in dataset["queries"]:
        assert query["relevant_docs"]


def _hash_setup():
    dataset = load_retrieval_dataset()
    provider = HashEmbeddingProvider()
    manager = KnowledgeManager()
    retriever = build_dataset_fixture(manager, dataset, embed_fn=provider.as_embed_fn(),
                                      embed_model_id=provider.model_id)
    return dataset, manager, retriever


def test_hash_fixture_runs_every_query_shape():
    dataset, _, retriever = _hash_setup()
    seen_strategies = set()
    for query in dataset["queries"]:
        items = retriever.retrieve(str(query["text"]), top_k=5)
        assert isinstance(items, list)
        if items:
            seen_strategies.add(items[0].strategy)
            assert retriever.last_quality is not None
    assert RetrievalStrategy.EXACT_TERM in seen_strategies
    assert RetrievalStrategy.HYBRID in seen_strategies or RetrievalStrategy.SEMANTIC in seen_strategies


def test_weight_grid_is_deterministic_and_reports():
    dataset = load_retrieval_dataset()
    provider = HashEmbeddingProvider()

    def factory(kw, vw):
        manager = KnowledgeManager()
        build_dataset_fixture(manager, dataset, embed_fn=provider.as_embed_fn(), embed_model_id=provider.model_id)
        return HybridRetriever(manager.index, manager.embeddings, embed_fn=provider.as_embed_fn(),
                               keyword_weight=kw, vector_weight=vw)

    first = evaluate_weight_grid(factory, dataset)
    second = evaluate_weight_grid(factory, dataset)
    assert first["best"] == second["best"]
    assert len(first["rows"]) == 5
    default = next(r for r in first["rows"] if (r["keyword_weight"], r["vector_weight"]) == (0.4, 0.6))
    assert first["best"]["mrr"] - default["mrr"] <= 0.2  # shipped default stays competitive
    assert all(0.0 <= r["mrr"] <= 1.0 for r in first["rows"])


def test_empty_and_irrelevant_queries():
    _, _, retriever = _hash_setup()
    assert retriever.retrieve("", top_k=5) == []
    items = retriever.retrieve("xyzzqy improbable nonsense", top_k=5)
    assert isinstance(items, list)
    assert RetrievalQuality.mrr([], ["router.md"]) == 0.0
    assert RetrievalQuality.mrr(["router.md#c0"], []) == 0.0


def test_doc_mapping_and_scoring_helpers():
    assert doc_of_chunk("ttl_v1.md#c2", {"document_id": "ttl_v1.md"}) == "ttl_v1.md"
    assert doc_of_chunk("plain#c0") == "plain"
    assert rank_docs([{"chunk_id": "a#c0"}, {"chunk_id": "b#c1"}, {"chunk_id": "a#c1"}]) == ["a", "b"]
    scored = score_query(["router.md", "ops.md"], ["router.md", "ops.md"])
    assert scored == {"precision_at_k": 1.0, "recall": 1.0, "mrr": 1.0}


# --------------------------------------------------
# live real-embedding leg (skips honestly when weights absent)
# --------------------------------------------------

@pytest.fixture(scope="module")
def live_provider():
    provider = SentenceTransformerEmbeddingProvider()
    if not provider.available():
        pytest.skip("sentence-transformers weights unavailable")
    assert provider.dimension == 384
    assert provider.normalized is True
    return provider


@pytest.fixture(scope="module")
def live_setup(live_provider):
    dataset = load_retrieval_dataset()
    manager = KnowledgeManager()
    retriever = build_dataset_fixture(
        manager, dataset,
        embed_fn=live_provider.as_embed_fn(),
        embed_batch_fn=live_provider.embed_batch,
        embed_model_id=live_provider.model_id,
    )
    return dataset, manager, retriever, live_provider


def test_live_semantic_and_paraphrase_rank_correct_doc(live_setup):
    dataset, _, retriever, _ = live_setup
    by_id = {q["id"]: q for q in dataset["queries"]}
    semantic = rank_docs([i.as_dict() for i in retriever.retrieve(by_id["semantic-router"]["text"], top_k=5)])
    assert semantic[0] == "router.md"
    paraphrase = rank_docs([i.as_dict() for i in retriever.retrieve(by_id["paraphrase-cache"]["text"], top_k=5)])
    assert paraphrase[0] == "cache.md"


def test_live_freshness_conflict_history_metadata(live_setup):
    dataset, _, retriever, _ = live_setup
    by_id = {q["id"]: q for q in dataset["queries"]}
    fresh = retriever.retrieve(by_id["fresh-ttl"]["text"], top_k=5)
    assert fresh[0].strategy == RetrievalStrategy.FRESHNESS_AWARE
    assert rank_docs([i.as_dict() for i in fresh])[0] == "ttl_v2.md"  # newer wins
    conflict = retriever.retrieve(by_id["conflict-ttl"]["text"], top_k=5)
    conflicts = detect_conflicts([i.as_dict() for i in conflict], topic="cache TTL")
    assert conflicts and conflicts[0].source_a != conflicts[0].source_b
    history = retriever.retrieve(by_id["history-router"]["text"], top_k=5)
    assert history[0].strategy == RetrievalStrategy.TASK_HISTORY
    assert rank_docs([i.as_dict() for i in history])[0] == "ops.md"
    meta = retriever.retrieve(by_id["metadata-source"]["text"], top_k=5)
    assert meta and all((i.provenance.source if i.provenance else "") == "runbook" for i in meta)


def test_live_provenance_carries_model_identity(live_setup):
    _, manager, _, live_provider = live_setup
    record = manager.embeddings.get("router.md#c0")
    assert record is not None
    prov = record["metadata"]["provenance"]
    assert prov["document_id"] == "router.md"
    assert prov["source"] == "docs"
    assert prov["version"] == "3"
    assert prov["indexed_at"]
    assert record["metadata"]["embedding_model"] == live_provider.model_id
    assert record["metadata"]["embedding_dim"] == 384


def test_live_end_to_end_grounded_quality(live_setup):
    _, _, retriever, _ = live_setup
    items = [i.as_dict() for i in retriever.retrieve("which component selects adapters", top_k=3)]
    grounded = ground_answer(["The model router selects adapters"], items)
    assert grounded[0]["evidence"]["kind"] == "direct"
    assert grounded[0]["evidence"]["chunk_id"].startswith("router.md")
    quality = retriever.last_quality
    assert quality.result_count > 0 and quality.latency_ms >= 0
    assert quality.precision_at_k(["router.md#c0", "router.md#c1"], 3, [i["chunk_id"] for i in items]) >= 0.5
    assert quality.recall(["router.md#c0"], [i["chunk_id"] for i in items]) >= 0.5
    assert quality.mrr([i["chunk_id"] for i in items], ["router.md#c0"]) == 1.0


def test_live_dim_mismatch_against_hash_index(live_setup):
    _, _, _, live_provider = live_setup
    index_manager = KnowledgeManager()
    hash_provider = HashEmbeddingProvider()
    build_dataset_fixture(index_manager, load_retrieval_dataset(),
                          embed_fn=hash_provider.as_embed_fn(), embed_model_id=hash_provider.model_id)
    mixed = HybridRetriever(index_manager.index, index_manager.embeddings,
                            embed_fn=live_provider.as_embed_fn())
    with pytest.raises(ValueError, match="EMBEDDING_DIMENSION_MISMATCH"):
        mixed.retrieve("model router selection research overview comparison", top_k=3)
