# ADR-011 — Resume semantics for side effects and compensation

Date: 2026-09-05 · Status: accepted

## Context

Resume replayed the full plan skipping verified steps — safe for
reads, unsafe as a universal rule (duplicate writes, interrupted
effectful steps of unknown outcome, stale policy/tools).

## Decision

Explicit effect classes with conservative defaults, claim
validation (never looser than the default), and a resume planner
that decides per step from recorded state: SKIP (read-only
verified), REPLAY (fresh/verified-not-complete/idempotent-safe,
always revalidated), COMPENSATE (declared, validated, verified
compensation first), BLOCK (effectful-verified, unknown mid-run
state, non-resumable attempts, changed policy/tools, missing
compensation, false idempotency, malformed checkpoints). Blocked
resumes park the task (PAUSED) with reasons instead of failing it.
Delivery semantics are documented per class and never exactly-once.

## Consequences

- Unsafe replay is structurally impossible without an explicit
  `replay-ok` policy or a validated compensation.
- Interruption states are recorded facts (`running` markers,
  verification presence), not guesses.
