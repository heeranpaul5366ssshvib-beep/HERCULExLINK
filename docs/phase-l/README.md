# Phase L — Canonical Boot Path + Safe Resume

## Boot (Part A–D)

`boot.py` no longer calls `ModelManager.generate` directly. `main()`
initializes through `RuntimeInitializer` (the single runtime path —
models, embeddings config, permissions, memory, tools, observability)
and serves every line via `HerculeCli.handle_line`:

- empty/exit preserved (`exit|quit|shutdown`);
- `classify_request` (existing `RequestRouter` + capability inference):
  CHAT without capabilities → QUESTION → `brain.think` (no task);
  `/commands` and capability-bearing requests → GOAL → `Brain.run_cycle`
  (TaskManager + policy + verification + tracing + memory/experience).
- `UniversalFallbackManager` (fabricated success strings) is retired:
  its methods now raise a deprecation error; init failure exits
  honestly. `auto_heal_project` untouched (out of scope).

## Resume (Parts E–O)

- Effect classes (`cognition/capabilities/effects.py`):
  READ_ONLY < IDEMPOTENT < EFFECTFUL < COMPENSATABLE < NON_RESUMABLE,
  with conservative per-capability defaults and documented
  (never exactly-once) semantics. Declared classes must be at least
  as restrictive as the default — false idempotency is rejected.
- Step metadata (`effect`, `state_check`, `compensation`,
  `resume_policy`) is additive to the PlanStep-compatible contract.
- `orchestrator/resume.py` (`ResumePlanner`): restores checkpoints,
  classifies VERIFIED COMPLETE / VERIFIED NOT COMPLETE / UNKNOWN,
  revalidates policy/health/environment, decides SKIP / REPLAY /
  COMPENSATE / BLOCK, runs read-only state checks and declared
  compensations (capability + permission validated, verified).
- `Brain.run_cycle` routes tasks with prior progress through the
  planner first: blocked → task parked (PAUSED) with a structured
  `blocked` result; compensations run before the loop; replayable
  states reopen. Fresh tasks behave exactly as before.
- Checkpoints now record effect, resume policy, compensation,
  environment, input fingerprint (no secrets), and timestamp.
- In-flight marking: the loop persists `running` at step start, so
  UNKNOWN (interrupted) vs VERIFIED COMPLETE vs VERIFIED NOT COMPLETE
  is a recorded distinction; duplicate invocation while a step is
  marked running reports in-progress without double-executing.
- Traces: `resume_attempt` + `compensation` stages and four WHY_*
  explainers derived from decision metadata.

## Performance (measured, §S)

classify ~12ms (first-import dominated) · CLI→Brain handle ~37ms
end-to-end · resume decision ~3ms · Brain→Loop overhead unchanged
from Phase K (~49ms, model reasoning dominates). No optimization
claimed.
