# ADR-002 — Wrapper integration, no foundation rewrites

Date: 2026-09-05 · Status: accepted

## Context

Phase F needed new retrieval/context/routing/evaluation behavior, but
the Phase E foundation (Kernel, TaskManager, permissions, contracts,
ModelManager, MemoryManager) is verified by 49 tests.

## Decision

All Phase F capability is new modules composed around existing seams:

- `HybridRetriever` wraps `IndexManager`/`EmbeddingIndex`/`VectorMemory`.
- `AdvancedModelRouter` wraps `ModelRouter`; `generate_with_fallback`
  mirrors `ModelManager.generate` adapter handling.
- `ContextEngine` gained only an optional `budget_config` path.
- `KnowledgeManager` gained `ingest_document`/`hybrid_retrieve`.
- Evaluators observe TaskManager dicts and `EventBus` outputs.

Two genuine bugs were fixed in place (`store_vector`/`retrieve_vector`
called nonexistent methods; `VectorMemory.clear()` crashed with FAISS).

## Consequences

- Baseline suite passes unmodified; strict DeprecationWarnings clean.
- Dead code (`router/router.py`, legacy brain engines) left frozen for
  a dedicated deprecation pass, not removed opportunistically.
