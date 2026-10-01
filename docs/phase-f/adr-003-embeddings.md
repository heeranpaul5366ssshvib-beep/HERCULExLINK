# ADR-003 — Deterministic test-grade embeddings

Date: 2026-09-05 · Status: accepted

## Context

Ingestion and semantic retrieval need an embedding function, but tests
must be hermetic (no Ollama server, no model downloads) and
deterministic.

## Decision

- Default `hash_embed` (SHA-256 buckets, L2-normalized) is labeled
  test-grade in code and docs; it measures plumbing, ranking, and
  fusion — not semantic quality.
- The embedder is a `Callable[[str], List[float]]` parameter everywhere
  (`KnowledgeIngestionPipeline`, `HybridRetriever`,
  `KnowledgeManager.ingest_document/hybrid_retrieve`), so production
  wiring injects Ollama/transformers providers without code changes.
- Benchmarks assert relative behavior (relevant doc ranks first on
  near-duplicate fixtures), which holds for any reasonable embedder.

## Consequences

- Full suite runs offline and deterministically.
- Semantic-quality benchmarks must be re-run after wiring a real
  provider; recorded `RetrievalQuality` makes before/after comparable.
