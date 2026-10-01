# ADR-007 — Floors plus per-platform lock, validated startup

Date: 2026-09-05 · Status: accepted

## Context

Phase H left `pip install sentence-transformers faiss-cpu psutil`
unrecorded, and production selection had no startup gate: bad config
surfaced wherever it was first used.

## Decision

- `requirements.txt` keeps portable `>=` floors; new
  `requirements-lock.txt` pins the exact 51-package verified set for
  win-amd64/cp314, labeled per-platform with regeneration
  instructions. No fake universal lock.
- `validate_environment()` is read-only diagnostics (never installs);
  `validate_startup()` fails fast with a classified error before work
  is accepted, wired into `RuntimeInitializer` only when an embedding
  config is supplied.
- Embedding requests route through the capability router
  (`models/embeddings/routing.py`); the manager executes but never
  reselects. Manager timeouts (thread-bounded, opt-in) surface as
  taxonomy timeouts; traces carry hashes, never content.
- The pytest-asyncio loop-scope notice is resolved by pinning the
  documented future default (`function`), not by suppression.

## Consequences

- Reproducible installs per platform; honest skips offline.
- Production cutover is configuration (`mode: production`), proven by
  live ingestion/retrieval tests and a rerun benchmark with quality
  identical to baseline.
