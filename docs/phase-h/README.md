# Phase H — Production Embedding Config + Learning Migration

## Part A — configuration-driven embeddings

`system/config/embedding_config.py`: `EmbeddingConfig` (provider,
model, dimension, normalization, device, batch size, cache, fallback,
mode) loaded as explicit-dict > `HERCULE_*` env > mode defaults.
`resolve_embedding_provider` implements configured → validate →
health → use, then fallback, else a structured `EmbeddingConfigError`
(no silent substitution).

Full reference: `embedding-config.md`.

## Part B — learning owns proposals, not storage

`cognition/learning/learning_manager.py: LearningEngine` is now the
evaluated-experience → proposal → validation → promotion pipeline.
The orphan `_knowledge` KV store is removed; legacy methods raise a
migration error (no hidden second store). Details: `learning.md`.

## ADRs

- ADR-005 `adr-005-learning-migration.md` — why removal, not adapter.
- ADR-006 `adr-006-embedding-config.md` — why config-driven selection
  with fail-closed modes.
