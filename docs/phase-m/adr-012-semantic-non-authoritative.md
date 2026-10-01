# ADR-012 — Semantic proposal is non-authoritative

Date: 2026-09-05 · Status: accepted

## Context

Keyword inference misses paraphrases and implicit requirements, but
letting a model drive execution would collapse the propose/decide/
authorize/verify separation built across Phases J–L.

## Decision

A model-backed proposer generates CANDIDATES through a hybrid
resolver (normalize → dedupe → conflict notes → deterministic gate);
the existing registry + health + policy validator remains the sole
authority, and confidence never authorizes. Deterministic inference
stays default and byte-identical; semantic mode is opt-in per flags,
with shadow evaluation and proposal-only caching. Timeouts the
backend cannot enforce are reported, not claimed.

## Consequences

- Measured on scripted mocks: hybrid F1 0.838 vs deterministic 0.720
  on the bundled dataset, with all semantic failure modes falling
  back safely. Live-model quality is explicitly unevaluated.
- Any future model plugs into `generate()` + router selection with no
  architectural change; the validator needs none.
