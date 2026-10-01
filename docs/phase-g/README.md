# Phase G — Real Embedding + Retrieval Intelligence

The embedding seam is now backed by a real local provider
(sentence-transformers, 384-dim) behind one authoritative interface,
with honest unavailability, dimension enforcement, caching, batching,
router selection, and measured benchmarks.

## Architecture

- Interface: `models/embeddings/provider.py` — `EmbeddingProvider` ABC
  (embed/embed_batch, model_id, dimension, normalized, device,
  available/health) + typed errors (`EMBEDDING_UNAVAILABLE`,
  `EMBEDDING_DIMENSION_MISMATCH`, `EMBEDDING_MALFORMED`) + `validate_vector`
  + `text_fingerprint` (hashes for logs/traces, never raw text).
- Providers: `sentence_transformer_provider.py` (lazy load, normalized
  once, real batching), `ollama_provider.py` (refuses the in-repo hash
  stub explicitly), `hash_provider.py` (deterministic, `test_only`).
- Facade: `models/embeddings/embedding_manager.py` — named providers,
  model-bound cache (`cache.py`: text-hash + model id + version keys,
  dim re-validation), resource-aware batch splitting, routing-outcome
  recording, legacy `create/batch` preserved.
- Selection: `ModelCapabilityRegistry.embedding_models()` +
  `register_embedding_models()` (MiniLM-384/cpu, nomic-768/ollama,
  hash-64/test-only) + `AdvancedModelRouter.route_embedding()`
  (capability=EMBEDDING → model id → provider; execution stays in
  `EmbeddingManager`).
- Compatibility: `EmbeddingIndex.require_dimension` + add-time check,
  `VectorMemory(dim, backend)` + add/search checks, `FaissAdapter` dim
  + finite checks, `HybridRetriever` strict query-dim validation on
  vector strategies (exact-term stays lexical-only and immune).
- Index lifecycle: `FaissAdapter.save/load/clear`, `VectorMemory.persist/
  restore` (dim-tagged manifest; corrupt data raises).
- Ingestion (`KnowledgeManager.ingest_document`): batch-per-document
  embedding, `embedding_model`/`embedding_dim` in chunk metadata and
  provenance (`embed:<model>` transformation step), optional FAISS
  mirror via `vector_store=`.
- Observability: `trace_embedding`/`trace_retrieval` (hashes + ids only);
  failures via `classify_embedding_error` (existing taxonomy, no new
  categories).
- Hermetic tests: `tests/conftest.py` forces HF/TRANSFORMERS offline
  (cache-only loads); missing weights → honest skips.

## What was NOT changed

Kernel, TaskManager, permissions, contracts, `ModelManager`,
`MemoryManager` semantics, default fusion weights (0.4/0.6 kept —
§benchmarks), `LearningEngine._knowledge` (documented in
`learning-silo.md`, migration deferred).
