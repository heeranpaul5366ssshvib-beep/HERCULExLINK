# Phase K — Canonical Brain → AutonomousLoop Integration

## Previous vs canonical path

- LEGACY (deprecated, functional): `run_cycle → orchestrator.pipeline`
  (`_reason/_plan/_execute/_memory` stages): model text per step via
  executor, no TaskManager, no policy, no verification. Still present
  for direct pipeline users; `run_cycle` no longer calls it.
- ACTIVE (separate concern, unchanged): `Brain.execute(route)` explicit
  dispatch, `Brain.think` non-executing reasoning.
- CANONICAL (new): `run_cycle` composes the verified `AutonomousLoop`
  with the orchestrator's own TaskManager/AbilityManager/Memory —
  plan validation, capability resolution, policy, execution,
  verification, replan, durable persistence, experience recording.

## Brain.run_cycle contract

`(prompt, steps?, task_id?, correlation_id?, payload_fn?)` →
`{task_id, status, result, verification, retries, replans,
execution_summary, correlation_id, latency_ms, error?}`. No reasoning
text. Idempotent replays (COMPLETED → cached report), in-progress
guard for verifiable in-flight work, PAUSED auto-resume,
`cancel/pause/resume_task` delegation, per-step CANCELLED checks, and
resume-skipping of verified-complete steps (replan ids are unique).

## Compatibility fixes

- `AbilityManager.ensure_defaults()`: idempotent gap-fill (the empty
  registry made test disables no-ops and starved matching).
- `ToolMatcher.execute_candidate`: scalar payloads pass through
  (previously `dict()`-coerced and crashed); agent envelopes merge.
- `step_verifier`: explicit `error`-keyed results fail every
  verification method; research-family verification honors declared
  `expected_outputs` (mis-bound tools refused); full capability
  dispatch table.

## Performance (measured)

Legacy pipeline 0.40ms vs canonical 49ms on the same stack — the
canonical path is slower because it performs validation, policy
checks, durable transitions, verification, tracing, and memory
writes the legacy path skips. No improvement claimed.
