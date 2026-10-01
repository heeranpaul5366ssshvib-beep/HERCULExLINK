# ADR-009 — Brain.run_cycle uses AutonomousLoop

Date: 2026-09-05 · Status: accepted

## Context

Phase J verified `AutonomousLoop` in isolation while `Brain.run_cycle`
still executed the legacy pipeline (model text per step, no task,
policy, or verification) — the highest-priority integration gap.

## Decision

`run_cycle` now composes (never duplicates) the loop:
orchestrator-first services (its TaskManager/abilities/memory),
capability planning, durable lifecycle transitions around the run
(CREATED→QUEUED→RUNNING→COMPLETED/FAILED, cancel-aware),
post-run memory + experience recording (failures recorded with
success 0.0, never as successes), and a structured result contract
without reasoning traces. Legacy stages are marked DEPRECATED but
functional; `test_pipeline.py` was migrated to pin the canonical
contract (stronger assertions: lifecycle + verification +
correlation, documented in-file).

## Consequences

- One authoritative execution path; policy/verification unbypassable
  from Brain (proven by denial, injection, and false-binding tests).
- Resume skips verified steps; duplicates and in-flight re-entry are
  idempotent; cancelled tasks leave no orphans.
