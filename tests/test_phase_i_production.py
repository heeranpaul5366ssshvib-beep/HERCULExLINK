"""Phase I: production cutover, index safety, cache, router authority, failures."""

import json
import time

import pytest

from evaluation.failures import FailureCategory, classify_embedding_error
from knowledge.knowledge_manager import KnowledgeManager
from memory.vector.vector_manager import VectorMemory
from models.embeddings.embedding_manager import EmbeddingManager
from models.embeddings.hash_provider import HashEmbeddingProvider
from models.embeddings.provider import EmbeddingError, EmbeddingMalformedError, EmbeddingUnavailableError
from models.embeddings.routing import route_and_embed, select_embedding_model
from models.router.advanced_router import AdvancedModelRouter, ModelRoutingFailure
from models.router.model_router import ModelRouter
from runtime.initializer import RuntimeInitializer
from system.observability.trace import Tracer


@pytest.fixture(scope="module")
def live_provider():
    from models.embeddings.sentence_transformer_provider import SentenceTransformerEmbeddingProvider

    provider = SentenceTransformerEmbeddingProvider()
    if not provider.available():
        pytest.skip("production weights unavailable")
    return provider


def test_production_cutover_uses_configured_provider(live_provider):
    services = RuntimeInitializer().initialize({"mode": "production"})
    manager = services["embeddings"]
    assert manager.default_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert services["embedding_report"]["selected"]["fallback"] is False
    vector = manager.embed("production cutover probe")
    assert len(vector) == 384


def test_ci_and_default_paths():
    ci_services = RuntimeInitializer().initialize({"mode": "ci"})
    assert ci_services["embeddings"].default_model == "hercule-hash-test-v1"
    plain = RuntimeInitializer().initialize()
    assert "embeddings" not in plain


def test_legacy_manifest_without_metadata_loads(tmp_path):
    store = VectorMemory(dim=4, backend="memory")
    store.add("legacy text here", [1.0, 0.0, 0.0, 0.0], {"chunk_id": "d#c0"})
    target = store.persist(tmp_path / "legacy")  # no index_metadata written
    manifest = json.loads((target / "store.json").read_text(encoding="utf-8"))
    assert "index_metadata" not in manifest
    restored = VectorMemory.restore(target, backend="memory")
    assert len(restored) == 1
    assert restored.search([1.0, 0.0, 0.0, 0.0], top_k=1)[0]["metadata"]["chunk_id"] == "d#c0"


def test_cache_disabled_versioned_and_model_scoped():
    manager = EmbeddingManager(use_cache=False)
    manager.register_provider(HashEmbeddingProvider(dim=8, model_id="hash-8"))
    first = manager.embed("cache probe", model="hash-8")
    assert manager.embed("cache probe", model="hash-8") == first
    assert manager.cache.stats.hits == 0  # disabled: no hits recorded
    assert len(manager.cache) == 0

    scoped = EmbeddingManager()
    scoped.register_provider(HashEmbeddingProvider(dim=8, model_id="model-a"))
    scoped.register_provider(HashEmbeddingProvider(dim=8, model_id="model-b"))
    scoped.embed("same text", model="model-a")
    assert scoped.cache.stats.misses == 1
    scoped.embed("same text", model="model-b")  # same text, other model: miss
    assert scoped.cache.stats.misses == 2
    assert len(scoped.cache) == 2
    scoped.cache.version = "2"  # config version bump invalidates logically
    assert scoped.cache.get("same text", "model-a") is None


def test_live_ingestion_path_uses_production_provider(live_provider):
    t0 = time.perf_counter()
    knowledge = KnowledgeManager()
    knowledge.ingest_document(
        "prod.md", "The model router selects adapters by health checks. " * 10,
        source="production-test", embed_fn=live_provider.as_embed_fn(),
        embed_batch_fn=live_provider.embed_batch, embed_model_id=live_provider.model_id,
    )
    ingest_ms = (time.perf_counter() - t0) * 1000.0
    assert ingest_ms > 0
    descriptor = knowledge.index_descriptor()
    assert descriptor["model_id"] == live_provider.model_id
    assert descriptor["dimension"] == 384
    assert knowledge.check_index_compatibility(live_provider) is not None
    t0 = time.perf_counter()
    hits = knowledge.hybrid_retrieve("which component selects adapters", top_k=3,
                                     embed_fn=live_provider.as_embed_fn())
    query_ms = (time.perf_counter() - t0) * 1000.0
    assert query_ms >= 0
    assert hits and hits[0]["chunk_id"].startswith("prod.md")
    assert hits[0]["provenance"]["metadata"]["embedding_model"] == live_provider.model_id


def test_router_authority_over_manager_selection():
    router = AdvancedModelRouter(ModelRouter())
    manager = EmbeddingManager()
    with pytest.raises(EmbeddingUnavailableError):
        select_embedding_model("embed this", router, manager)  # nothing registered: no swap
    manager.register_provider(HashEmbeddingProvider(model_id="sentence-transformers/all-MiniLM-L6-v2", dim=384))
    chosen = select_embedding_model("embed this", router, manager)
    assert chosen == "sentence-transformers/all-MiniLM-L6-v2"
    assert route_and_embed(manager, router, "hello", task="embed this") is not None
    assert len(route_and_embed(manager, router, ["a", "b"], task="embed this", batch=True)) == 2
    with pytest.raises(ModelRoutingFailure):
        router.route_embedding("embed this", preferred_model="ghost-model")


def test_manager_traces_without_content():
    tracer = Tracer()
    manager = EmbeddingManager(tracer=tracer)
    manager.register_provider(HashEmbeddingProvider(dim=8, model_id="hash-8"))
    manager.embed("trace me", model="hash-8", correlation_id="corr-i")
    manager.embed("trace me", model="hash-8", correlation_id="corr-i")  # hit
    manager.embed_batch(["one", "two"], model="hash-8", correlation_id="corr-i")
    stages = tracer.get("corr-i").as_dict()["stages"]["embedding"]
    assert len(stages) == 3
    assert stages[0]["cache_hit"] is False and stages[1]["cache_hit"] is True
    blob = json.dumps(stages)
    assert "trace me" not in blob  # hashes only


def test_timeout_surfaces_and_classifies():
    import time as _time

    class SlowProvider(HashEmbeddingProvider):
        def embed(self, text):
            _time.sleep(0.5)
            return super().embed(text)

    manager = EmbeddingManager(timeout_s=0.05)
    manager.register_provider(SlowProvider(dim=8, model_id="slow-8"))
    with pytest.raises(EmbeddingError, match="timed out"):
        manager.embed("too slow", model="slow-8")
    try:
        manager.embed("too slow", model="slow-8")
    except EmbeddingError as exc:
        record = classify_embedding_error(exc)
        assert record.category == FailureCategory.NETWORK


def test_malformed_provider_vector_rejected():
    class BadProvider(HashEmbeddingProvider):
        def embed(self, text):
            return ["not"] * 8  # right dim, non-numeric components

    manager = EmbeddingManager()
    manager.register_provider(BadProvider(dim=8, model_id="bad-8"))
    with pytest.raises(EmbeddingMalformedError):
        manager.embed("x", model="bad-8")
    record = classify_embedding_error(EmbeddingMalformedError("nan component"))
    assert record.retryable is False
