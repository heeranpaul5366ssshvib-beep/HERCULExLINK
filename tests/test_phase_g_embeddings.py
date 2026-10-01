"""Phase G: embedding providers, manager/cache, validation, lifecycle."""

import math

import pytest

from evaluation.failures import FailureCategory, classify_embedding_error
from knowledge.datasets import build_dataset_fixture, load_retrieval_dataset
from knowledge.embeddings.embedding_index import EmbeddingIndex
from knowledge.hybrid_retrieval import HybridRetriever, RetrievalStrategy
from knowledge.indexing.index_manager import IndexManager
from knowledge.ingestion import KnowledgeIngestionPipeline, hash_embed
from knowledge.knowledge_manager import KnowledgeManager
from memory.vector.vector_manager import VectorMemory
from models.capabilities import ModelCapabilityRegistry, register_embedding_models
from models.embeddings.cache import EmbeddingCache
from models.embeddings.embedding_manager import EmbeddingManager
from models.embeddings.hash_provider import HashEmbeddingProvider
from models.embeddings.ollama_provider import OllamaEmbeddingProvider
from models.embeddings.provider import (
    EmbeddingDimensionMismatchError,
    EmbeddingMalformedError,
    EmbeddingUnavailableError,
    text_fingerprint,
    validate_vector,
)
from models.embeddings.sentence_transformer_provider import SentenceTransformerEmbeddingProvider
from models.router.advanced_router import AdvancedModelRouter, ModelRoutingFailure
from models.router.model_router import ModelRouter
from models.routing_performance import RoutingMemory
from system.observability.trace import Tracer, trace_embedding, trace_retrieval


# --------------------------------------------------
# interface + validation
# --------------------------------------------------

def test_provider_interface_conformance():
    providers = [
        HashEmbeddingProvider(),
        OllamaEmbeddingProvider(model_id="no-such-model-xyz", host="http://127.0.0.1:9"),
        SentenceTransformerEmbeddingProvider(model_id="no-such-model-xyz"),
    ]
    for provider in providers:
        health = provider.health()
        assert set(health) >= {"status", "available", "model_id", "dimension"}
        assert isinstance(provider.available(), bool)
        assert provider.model_id
    # Unavailable backends raise honestly — never fake vectors.
    for provider in providers[1:]:
        assert provider.available() is False
        with pytest.raises(EmbeddingUnavailableError):
            provider.embed("hello")


def test_hash_provider_is_deterministic_test_grade():
    provider = HashEmbeddingProvider()
    assert provider.test_only is True
    assert provider.health()["test_only"] is True
    assert provider.embed("router health") == provider.embed("router health")
    assert len(provider.embed_batch(["a", "b"])) == 2
    assert provider.normalized is True
    with pytest.raises(EmbeddingMalformedError):
        provider.embed(123)


def test_validate_vector_rejects_loudly():
    assert validate_vector([1.0, 0.0], 2) == [1.0, 0.0]
    with pytest.raises(EmbeddingDimensionMismatchError) as info:
        validate_vector([1.0], 2)
    assert "EMBEDDING_DIMENSION_MISMATCH" in str(info.value)
    for bad in ([], "nope", [1.0, float("nan")], [1.0, float("inf")], [1.0, "x"]):
        with pytest.raises(EmbeddingMalformedError):
            validate_vector(bad, 0 if bad == [] else 2)


def test_fingerprint_never_leaks_content():
    fp = text_fingerprint("super secret document contents")
    assert len(fp) == 12
    assert "secret" not in fp
    assert text_fingerprint("a") != text_fingerprint("b")
    assert text_fingerprint("a") == text_fingerprint("a")


# --------------------------------------------------
# cache
# --------------------------------------------------

def test_cache_is_model_bound():
    cache = EmbeddingCache()
    cache.put("hello", "model-a", [1.0, 0.0])
    assert cache.get("hello", "model-a", 2) == [1.0, 0.0]
    assert cache.get("hello", "model-b", 2) is None  # no cross-model reuse
    assert cache.get("other", "model-a", 2) is None
    assert cache.stats.hit_rate == pytest.approx(1 / 3)
    cache.put("hello", "model-a", [1.0, 0.0, 0.0])  # dim drift under same key
    assert cache.get("hello", "model-a", 2) is None  # evicted, miss
    assert len(cache) == 0
    cache.put("x", "m", [1.0])
    assert cache.invalidate_model("m") == 1


# --------------------------------------------------
# manager
# --------------------------------------------------

def _manager():
    manager = EmbeddingManager()
    manager.register_provider(HashEmbeddingProvider(dim=8, model_id="hash-8"))
    manager.register_provider(HashEmbeddingProvider(dim=16, model_id="hash-16"))
    return manager


def test_manager_embed_caches_and_isolates_models():
    manager = _manager()
    first = manager.embed("router health", model="hash-8")
    assert len(first) == 8
    assert manager.embed("router health", model="hash-8") == first
    assert manager.cache.stats.hits == 1
    other = manager.embed("router health", model="hash-16")
    assert len(other) == 16  # separate entry, no dim confusion
    assert manager.embed_batch(["a", "b"], model="hash-8") is not None
    assert manager.throughput_stats()["cache"]["hits"] >= 1
    assert set(manager.health()) == {"hash-8", "hash-16"}
    # Legacy API still works.
    assert manager.create("hash-8", "router health") == first
    assert len(manager.batch("hash-8", ["a"])) == 1
    with pytest.raises(EmbeddingUnavailableError):
        manager.embed("x", model="missing-model")


def test_manager_records_routing_outcomes():
    memory = RoutingMemory()
    manager = EmbeddingManager(routing_memory=memory)
    manager.register_provider(HashEmbeddingProvider(dim=8, model_id="hash-8"))
    manager.embed("hello", model="hash-8")
    assert memory.stats_for("hash-8", "embedding").samples == 1
    broken = HashEmbeddingProvider(dim=8, model_id="broken")
    broken.embed = lambda text: (_ for _ in ()).throw(RuntimeError("boom"))
    manager.register_provider(broken)
    with pytest.raises(RuntimeError):
        manager.embed("hello", model="broken")
    assert memory.stats_for("broken", "embedding").failures == 1


def test_manager_batch_size_shrinks_under_pressure():
    manager = _manager()
    assert manager._effective_batch_size() == 32
    pressured = EmbeddingManager(resource_fn=lambda: {"source": "psutil", "cpu_percent": 99.0, "ram_percent": 99.0})
    assert pressured._effective_batch_size() == 8


# --------------------------------------------------
# registry + routing
# --------------------------------------------------

def test_embedding_model_registry_and_router():
    registry = ModelCapabilityRegistry()
    assert register_embedding_models(registry) == register_embedding_models(registry)
    assert len(registry.embedding_models()) == 2  # test-only hash excluded
    assert len(registry.embedding_models(min_score=0.0, include_test_only=True)) == 3
    router = AdvancedModelRouter(ModelRouter(), capabilities=registry)
    model_id, decision = router.route_embedding()
    assert model_id == "sentence-transformers/all-MiniLM-L6-v2"
    assert decision.task_type == "embedding"
    assert "nomic-embed-text" in decision.fallback_chain
    only_big, _ = router.route_embedding(min_dimension=512)
    assert only_big == "nomic-embed-text"
    with pytest.raises(ModelRoutingFailure):
        router.route_embedding(preferred_model="no-such-model")


# --------------------------------------------------
# dimension enforcement
# --------------------------------------------------

def test_embedding_index_pins_dimension():
    index = EmbeddingIndex()
    index.add("a", [1.0, 0.0])
    index.require_dimension(2)
    with pytest.raises(ValueError) as info:
        index.add("b", [1.0])
    assert "EMBEDDING_DIMENSION_MISMATCH" in str(info.value)
    with pytest.raises(ValueError):
        index.require_dimension(3)
    with pytest.raises(ValueError):
        index.require_dimension(0)


def test_retriever_rejects_dim_mismatch_on_vector_strategies():
    index, embeddings = IndexManager(), EmbeddingIndex()
    pipeline = KnowledgeIngestionPipeline(index, embeddings, embed_fn=lambda t: hash_embed(t, 8))
    pipeline.ingest("doc.md", "router adapter health selection")
    retriever = HybridRetriever(index, embeddings, embed_fn=lambda t: hash_embed(t, 2))
    with pytest.raises(ValueError) as info:
        retriever.retrieve("router adapter comparison research overview", top_k=3)
    assert "EMBEDDING_DIMENSION_MISMATCH" in str(info.value)
    # Exact-term lookup never embeds: lexical path survives corrupt dims.
    exact = retriever.retrieve('"router"', top_k=3)
    assert exact and all(i.strategy == RetrievalStrategy.EXACT_TERM for i in exact)


def test_ingestion_batches_and_tags_provenance():
    calls = []

    def batch_fn(texts):
        calls.append(len(texts))
        return [hash_embed(t, 8) for t in texts]

    index, embeddings = IndexManager(), EmbeddingIndex()
    pipeline = KnowledgeIngestionPipeline(
        index, embeddings, chunk_size=5, overlap=0, embed_batch_fn=batch_fn, embed_model_id="batch-model"
    )
    result = pipeline.ingest("doc.md", "one two three four five six seven eight nine ten eleven twelve")
    assert result.chunk_count == 3
    assert calls == [3]  # one batch call, not one per chunk
    assert result.errors == []
    assert embeddings.expected_dim == 8
    prov = result.chunks[0].provenance
    assert prov.metadata["embedding_model"] == "batch-model"
    assert prov.metadata["embedding_dim"] == 8
    assert any(t.startswith("embed:") for t in prov.transformation)


def test_ingestion_batch_length_mismatch_is_reported():
    index, embeddings = IndexManager(), EmbeddingIndex()
    pipeline = KnowledgeIngestionPipeline(index, embeddings, chunk_size=2, overlap=0,
                                          embed_batch_fn=lambda texts: [[1.0]])
    result = pipeline.ingest("doc.md", "one two three four five six")
    assert result.chunk_count == 0
    assert any("embedding" in e for e in result.errors)


# --------------------------------------------------
# vector lifecycle (both backends)
# --------------------------------------------------

def _fill(store):
    store.add("alpha marker text", [1.0, 0.0, 0.0, 0.0], {"chunk_id": "d#c0"})
    store.add("beta marker text", [0.0, 1.0, 0.0, 0.0], {"chunk_id": "d#c1"})


def test_vector_memory_backend_lifecycle(tmp_path):
    pytest.importorskip("faiss")
    store = VectorMemory(dim=4)
    assert store._backend is not None
    _fill(store)
    hits = store.search([1.0, 0.0, 0.0, 0.0], top_k=1)
    assert hits and hits[0]["metadata"]["chunk_id"] == "d#c0"
    with pytest.raises(ValueError) as info:
        store.add("wrong", [1.0, 0.0])
    assert "EMBEDDING_DIMENSION_MISMATCH" in str(info.value)
    target = store.persist(tmp_path / "faiss-store")
    restored = VectorMemory.restore(target)
    assert len(restored) == 2
    assert restored.search([0.0, 1.0, 0.0, 0.0], top_k=1)[0]["metadata"]["chunk_id"] == "d#c1"


def test_vector_memory_fallback_lifecycle(tmp_path):
    store = VectorMemory(dim=4, backend="memory")
    assert store._backend is None
    _fill(store)
    assert store.search([1.0, 0.0, 0.0, 0.0], top_k=1)[0]["metadata"]["chunk_id"] == "d#c0"
    target = store.persist(tmp_path / "mem-store")
    restored = VectorMemory.restore(target, backend="memory")
    assert len(restored) == 2
    store.clear()
    assert len(store) == 0


def test_vector_restore_rejects_corruption(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "store.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        VectorMemory.restore(broken)
    mismatch = tmp_path / "mismatch"
    mismatch.mkdir()
    (mismatch / "store.json").write_text('{"dim": 4, "backend": "memory", "count": 1}', encoding="utf-8")
    (mismatch / "records.json").write_text('{"dim": 8, "records": []}', encoding="utf-8")
    with pytest.raises(ValueError) as info:
        VectorMemory.restore(mismatch)
    assert "DIMENSION_MISMATCH" in str(info.value)


# --------------------------------------------------
# failures + observability
# --------------------------------------------------

def test_embedding_failures_use_existing_taxonomy():
    unavailable = classify_embedding_error(EmbeddingUnavailableError("server down"))
    assert unavailable.category == FailureCategory.MODEL
    assert unavailable.retryable is True
    mismatch = classify_embedding_error(EmbeddingDimensionMismatchError("EMBEDDING_DIMENSION_MISMATCH: x"))
    assert mismatch.code == "EMBEDDING_DIMENSION_MISMATCH"
    malformed = classify_embedding_error(EmbeddingMalformedError("nan component"))
    assert malformed.category == FailureCategory.INTERNAL and malformed.retryable is False
    generic = classify_embedding_error(RuntimeError("connection timeout"))
    assert generic.category == FailureCategory.NETWORK


def test_embedding_trace_records_hashes_not_text():
    tracer = Tracer()
    entry = trace_embedding(tracer, "corr-g", "minilm", 384, 4, 12.5, True, ["abc123"])
    assert entry["model_id"] == "minilm" and entry["cache_hit"] is True
    assert tracer.get("corr-g").as_dict()["stages"]["embedding"]
    retrieval = trace_retrieval(tracer, "corr-g", "hybrid", 3, 1.2, ["d#c0"])
    assert retrieval["hits"] == 3
    assert trace_embedding(None, "x")["model_id"] == ""
    assert trace_retrieval(None, "x")["strategy"] == ""
