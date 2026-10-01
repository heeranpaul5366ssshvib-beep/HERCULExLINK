# ADR-004 — One embedding interface, honest availability

Date: 2026-09-05 · Status: accepted

## Context

Phase F left three unconnected embedding paths: adapter
`embeddings()` methods, `EmbeddingManager(client)` Ollama passthrough
(never called), and the `embed_fn` callable defaulting to a hash.
Phase G had to add real providers without creating a second competing
abstraction, in an environment where heavy deps may be absent.

## Decision

- `EmbeddingProvider` ABC is the single contract; `EmbeddingManager`
  is the single facade (legacy `create/batch` preserved).
- Providers lazy-load and report unavailable honestly. The Ollama
  provider explicitly refuses the in-repo hash stub (`_HAS_OLLAMA`
  check) — stub vectors must never flow into a production index.
- Dimensions are pinned (`require_dimension`, store `dim`, strict
  query checks); mismatches raise `EMBEDDING_DIMENSION_MISMATCH`.
- Normalization happens exactly once, in the provider; cosine scoring
  stays scale-invariant downstream.
- `tests/conftest.py` pins HF/TRANSFORMERS offline so unit tests use
  cached weights or skip — never download mid-suite.

## Consequences

- Live sentence-transformers leg runs when weights are cached, skips
  otherwise; hash leg always runs for plumbing.
- Adding a backend = new `EmbeddingProvider` + registry entry; no
  manager/knowledge/memory changes required.
