# ADR-006 — Configuration-driven embedding selection

Date: 2026-09-05 · Status: accepted

## Context

Phase G proved real embeddings behind an injectable seam, but
selection was still call-site code: production could only be had by
passing the right objects, and nothing stopped a test-only provider
from reaching a production index.

## Decision

`system/config/embedding_config.py` owns selection: mode defaults
(per-mode provider table), `HERCULE_*` env, explicit-dict precedence,
CI forcing hash, and `resolve_embedding_provider` (validate → health →
use → fallback → coded failure). Test-only providers fail closed in
production even when explicitly configured. Validation errors fail
fast (fallback only covers *unavailability*). Index descriptors and
vector manifests bind provider/model/dim/normalized and are enforced
on load. `RuntimeInitializer.initialize(embedding_config=...)` wires
the resolved provider; the default path is untouched.

## Consequences

- Production selection is data (`config/hercule.json` "embeddings"
  section or env), not code edits in `KnowledgeManager`.
- `docs/phase-h/embedding-config.md` records why MiniLM-L6-v2 is the
  production default (measured MRR 1.0, cpu, 384-dim, cached weights).
- Single-candidate failures surface their specific code;
  multi-candidate exhaustion surfaces `EMBEDDING_NO_BACKEND` with the
  per-attempt trail for the trace.
