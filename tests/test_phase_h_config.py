"""Phase H-A: configuration-driven embedding selection + index compatibility."""

import pytest

from knowledge.knowledge_manager import KnowledgeManager
from memory.vector.vector_manager import VectorMemory
from models.embeddings.hash_provider import HashEmbeddingProvider
from runtime.initializer import RuntimeInitializer
from system.config.embedding_config import (
    EmbeddingConfig,
    EmbeddingConfigError,
    default_providers_for_mode,
    load_embedding_config,
    resolve_embedding_provider,
    validate_device,
)
from system.observability.trace import Tracer


def test_defaults_select_production_provider():
    config = load_embedding_config({}, env={})
    assert config.mode.value == "production"
    assert config.provider == "sentence-transformers"
    assert config.cache is True and config.batch_size == 32


def test_env_and_mode_precedence():
    config = load_embedding_config({}, env={"HERCULE_MODE": "test"})
    assert config.mode.value == "test" and config.provider == "hash"
    # CI forces hermetic provider regardless of configuration.
    forced = load_embedding_config({"provider": "sentence-transformers", "mode": "ci"}, env={})
    assert forced.provider == "hash" and forced.allow_test_providers is True
    override = load_embedding_config({"provider": "ollama", "model_id": "nomic-embed-text"},
                                     env={"HERCULE_EMBEDDING_PROVIDER": "hash"})
    assert override.provider == "ollama"  # explicit dict beats env
    with pytest.raises(EmbeddingConfigError):
        load_embedding_config({"mode": "nope"}, env={})
    with pytest.raises(EmbeddingConfigError):
        load_embedding_config({"dimension": "wide"}, env={})


def test_device_and_field_validation():
    validate_device("cpu")
    validate_device("cuda:0")
    with pytest.raises(EmbeddingConfigError) as info:
        validate_device("tpu-9")
    assert info.value.code == "EMBEDDING_BAD_DEVICE"
    empty = load_embedding_config({"provider": "hash", "model_id": "", "mode": "test"}, env={})
    with pytest.raises(EmbeddingConfigError) as bad:
        resolve_embedding_provider(empty)
    assert bad.value.code == "EMBEDDING_BAD_MODEL"


def test_unknown_provider_rejected_with_code():
    config = load_embedding_config({"provider": "telepathy", "mode": "test"}, env={})
    with pytest.raises(EmbeddingConfigError) as info:
        resolve_embedding_provider(config)
    assert info.value.code == "EMBEDDING_UNKNOWN_PROVIDER"


def test_test_provider_blocked_in_production():
    config = load_embedding_config({"provider": "hash", "mode": "production"}, env={})
    with pytest.raises(EmbeddingConfigError) as info:
        resolve_embedding_provider(config)
    assert info.value.code == "EMBEDDING_TEST_PROVIDER_BLOCKED"


def test_dimension_mismatch_rejected():
    config = load_embedding_config(
        {"provider": "hash", "model_id": "hercule-hash-test-v1", "dimension": 999,
         "mode": "test", "allow_test_providers": True}, env={})
    with pytest.raises(EmbeddingConfigError) as info:
        resolve_embedding_provider(config)
    assert info.value.code == "EMBEDDING_DIMENSION_MISMATCH"


def test_normalization_mismatch_rejected():
    config = load_embedding_config(
        {"provider": "ollama", "model_id": "nomic-embed-text", "normalized": True,
         "mode": "offline"}, env={})
    with pytest.raises(EmbeddingConfigError) as info:
        resolve_embedding_provider(config)
    assert info.value.code == "EMBEDDING_NORMALIZATION_MISMATCH"


def test_offline_fallback_is_explicit_and_traced():
    config = load_embedding_config(
        {"provider": "ollama", "model_id": "nomic-embed-text",
         "fallback_provider": "hash", "fallback_model_id": "hercule-hash-test-v1",
         "mode": "offline"}, env={})
    tracer = Tracer()
    provider, report = resolve_embedding_provider(config, tracer=tracer, correlation_id="corr-h")
    assert provider.model_id == "hercule-hash-test-v1"
    assert report["fallback_used"] is True
    assert len(report["attempts"]) == 2
    assert report["attempts"][0]["selected"] is False
    assert tracer.get("corr-h").as_dict()["stages"]["embedding"]


def test_no_backend_fails_clearly():
    config = load_embedding_config({"provider": "ollama", "mode": "offline"}, env={})
    with pytest.raises(EmbeddingConfigError) as info:
        resolve_embedding_provider(config)
    assert info.value.code == "EMBEDDING_BACKEND_UNAVAILABLE"
    both_dead = load_embedding_config(
        {"provider": "ollama", "fallback_provider": "ollama",
         "fallback_model_id": "other-missing-model", "mode": "offline"}, env={})
    with pytest.raises(EmbeddingConfigError) as chained:
        resolve_embedding_provider(both_dead)
    assert chained.value.code == "EMBEDDING_NO_BACKEND"
    assert "ollama" in str(chained.value)


def test_production_resolution_selects_real_provider():
    pytest.importorskip("sentence_transformers")
    from models.embeddings.sentence_transformer_provider import SentenceTransformerEmbeddingProvider

    probe = SentenceTransformerEmbeddingProvider()
    if not probe.available():
        pytest.skip("weights unavailable")
    config = load_embedding_config({}, env={})
    provider, report = resolve_embedding_provider(config)
    assert provider.model_id == "sentence-transformers/all-MiniLM-L6-v2"
    assert provider.dimension == 384
    assert report["selected"]["fallback"] is False


def test_mode_selection_orders():
    assert default_providers_for_mode("production")[0] == "sentence-transformers"
    assert default_providers_for_mode("ci") == ["hash"]


# --------------------------------------------------
# index compatibility
# --------------------------------------------------

def _hash_manager():
    manager = KnowledgeManager()
    manager.ingest_document("doc.md", "The model router selects adapters by health checks. " * 6,
                            source="unit-test", embed_model_id="hercule-hash-test-v1")
    return manager


def test_index_descriptor_and_compat_check():
    manager = _hash_manager()
    descriptor = manager.index_descriptor()
    assert descriptor["model_id"] == "hercule-hash-test-v1"
    assert descriptor["dimension"] == 64 and descriptor["chunks"] >= 1
    provider = HashEmbeddingProvider()
    manager.write_index_metadata()
    assert manager.check_index_compatibility(provider)["model_id"] == "hercule-hash-test-v1"
    with pytest.raises(ValueError, match="EMBEDDING_INDEX_INCOMPATIBLE"):
        manager.check_index_compatibility(model_id="other-model", dimension=64)
    with pytest.raises(ValueError, match="EMBEDDING_INDEX_INCOMPATIBLE"):
        manager.check_index_compatibility(model_id="hercule-hash-test-v1", dimension=999)
    with pytest.raises(ValueError, match="EMBEDDING_INDEX_INCOMPATIBLE"):
        manager.write_index_metadata({"model_id": "hercule-hash-test-v1", "dimension": 64, "normalized": False})
        manager.check_index_compatibility(provider)  # hash provider normalized=True


def test_mixed_index_descriptor_rejected():
    manager = KnowledgeManager()
    manager.embeddings.add("a#c0", [1.0, 0.0], {"embedding_model": "model-a"})
    manager.embeddings.add("b#c0", [1.0, 0.0], {"embedding_model": "model-b"})
    with pytest.raises(ValueError, match="EMBEDDING_INDEX_INCOMPATIBLE"):
        manager.index_descriptor()


def test_vector_manifest_carries_and_enforces_metadata(tmp_path):
    store = VectorMemory(dim=8, backend="memory")
    store.add("doc text here", [1.0] + [0.0] * 7, {"chunk_id": "d#c0"})
    meta = {"provider": "hash", "model_id": "hercule-hash-test-v1", "dimension": 8,
            "normalized": True, "version": "1"}
    target = store.persist(tmp_path / "store", index_metadata=meta)
    restored = VectorMemory.restore(target, backend="memory", expected=meta)
    assert len(restored) == 1
    with pytest.raises(ValueError, match="EMBEDDING_INDEX_INCOMPATIBLE"):
        VectorMemory.restore(target, backend="memory",
                             expected={**meta, "model_id": "other-model"})
    with pytest.raises(ValueError, match="EMBEDDING_INDEX_INCOMPATIBLE"):
        VectorMemory.restore(target, backend="memory", expected={**meta, "dimension": 16})
    with pytest.raises(ValueError, match="EMBEDDING_INDEX_INCOMPATIBLE"):
        VectorMemory.restore(target, backend="memory", expected={**meta, "normalized": False})
    # Absent expectations keep backward compatibility with old manifests.
    assert len(VectorMemory.restore(target, backend="memory")) == 1


def test_startup_wires_configured_embeddings():
    services = RuntimeInitializer().initialize({"mode": "test"})
    assert "embeddings" in services
    assert services["embedding_report"]["selected"]["provider"] == "hash"
    assert services["embeddings"].default_model == "hercule-hash-test-v1"
    plain = RuntimeInitializer().initialize()
    assert "embeddings" not in plain  # default path unchanged
