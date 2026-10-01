# Phase F — Intelligence Core 2.0

Measurable intelligence on top of the Phase E foundation. Additive only:
no changes to Kernel, durable TaskManager, permission enforcement,
ownership contracts, ModelManager, or MemoryManager semantics (two
bug-compatible fixes: `MemoryManager.store_vector/retrieve_vector` now
call the real `VectorMemory.add`, and `VectorMemory.clear()` is
backend-safe).

## Ownership boundaries

| Concern | Owner | Stores |
|---|---|---|
| KNOWLEDGE — world/reference material | `knowledge/` (`KnowledgeManager`, ingestion, hybrid retrieval, evidence) | `IndexManager`, `EmbeddingIndex`, `Ontology` |
| MEMORY — authorized interaction state | `memory/` (`MemoryManager`, unchanged semantics) | working/short/long/semantic/episodic/procedural/vector |
| EXPERIENCE — distilled task outcomes | `cognition/experience/` (`ExperienceManager`) | in-memory records + procedure proposals |

`ExperienceManager` observes TaskManager dicts read-only; procedures
promote only after repeated success + explicit validation.

## Module map

- Ingestion: `knowledge/ingestion.py`, provenance `knowledge/provenance.py`
- Retrieval: `knowledge/hybrid_retrieval.py` (+ `KnowledgeManager.ingest_document/hybrid_retrieve`)
- Evidence: `knowledge/evidence.py` (types, conflicts, freshness, grounding)
- Context: `cognition/context/priority.py` + `ContextEngine(budget_config=...)`
- Capabilities: `models/capabilities.py`; health `models/model_health.py`
- Routing: `models/router/advanced_router.py`; memory `models/routing_performance.py`
- Resources: `system/resources.py` (psutil when present, honest zeros otherwise)
- Evaluation: `evaluation/` (failures, metrics, benchmarks, engine)
- Traces: `system/observability/trace.py` (+ five `explain_*` helpers)

## Key behaviors

- Retrieval strategy is selected per query (exact/semantic/metadata/
  hybrid/freshness/task-history); every run records `RetrievalQuality`
  (latency, duplicate rate, precision@k/recall against judgments).
- Routing scores six factors (capability, availability, health, latency,
  resources, history); incapable models fail closed; total failure
  raises `ModelRoutingFailure` with the decision attached — never a
  silent success.
- Context priorities CRITICAL → DISCARDABLE; CRITICAL items are
  compressed, never silently dropped; every removal/compression is
  listed in `diagnostics`.
- Failures classify into 12 categories with retryable/fatal severity;
  `FailureLedger` aggregates recurrences for engineering action.
