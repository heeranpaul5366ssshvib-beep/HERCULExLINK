# ADR-005 — Remove the orphan KV silo, don't adapt it

Date: 2026-09-05 · Status: accepted

## Context

Phase G audit proved `LearningEngine._knowledge` orphaned (zero
callers) and duplicative. The Phase H brief allowed removal if
genuinely unused, or a compatibility adapter.

## Decision

Removal. An adapter would preserve a second knowledge-shaped store
under a new name — exactly what §13 forbids ("no second hidden
knowledge store"). Legacy method names survive only as loud shims
raising `RuntimeError` with the migration path, so any unknown caller
fails with guidance instead of silent success or bare
`AttributeError`. Learning's new role (evaluated intake → proposals →
validation → promotion) is incompatible with an unvalidated KV
`learn(key, value)` semantic, so keeping the methods functional would
lie about what learning means.

## Consequences

- `SemanticMemory` remains the KV memory; `ExperienceManager` the
  outcome store; `LearningEngine` the proposal pipeline.
- If an external caller surfaces, the error message migrates it in
  one step (intake requires evaluated evidence by design).
