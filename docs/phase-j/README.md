# Phase J — Capability-Aware Planning + Autonomous Execution

Bridge: GOAL → PLAN (with required capabilities) → VALIDATION →
capability resolution → TOOL/AGENT matching → POLICY → EXECUTION →
OBSERVATION → VERIFICATION → TASK UPDATE → REPLAN → COMPLETION.

## New modules

- `cognition/capabilities/`: `capability.py` (18 canonical
  capabilities + risk levels + coercion), `inference.py`
  (deterministic keyword inference, untrusted content yields nothing),
  `registry.py` (authoritative capability → tool/agent providers,
  live health, permission risk, environment-aware snapshot).
- `cognition/planner/capable.py`: enriched steps (id, objective,
  dependencies, capabilities, preferred/acceptable tools, inputs/
  outputs, expected state, verification criteria with per-capability
  defaults, risk, permissions, constraints, timeout, retry policy);
  `Planner.create_capable_plan` (legacy `create_plan` untouched).
- `cognition/planner/validation.py`: pre-execution gate (coverage,
  unknown/missing/unavailable capabilities, dependency + cycle checks,
  permission pre-check, verification presence) + §17 quality metrics.
- `abilities/tool_health.py`: READY/DEGRADED/UNAVAILABLE/FAILED states
  + prior-smoothed reliability tracker.
- `abilities/tool_matcher.py`: ranked matching (coverage .55, health
  .20, reliability .15, kind .10), permission pre-check, execution
  with classified fallback; destructive steps never blindly retried.
  Strict split: ModelRouter→model, ToolMatcher→tool,
  AgentManager→agent, Orchestrator→coordination.
- `orchestrator/step_verifier.py`: outcome verification per
  capability family (never "complete because the tool returned").
- `orchestrator/autonomous.py`: `AutonomousLoop` (preview + run with
  validation, fallback, replan-through-the-same-gate, durable task
  persistence of capability/tool/verification state).
- `system/observability/trace.py`: `trace_autonomy` (7 stages) + six
  explainers (plan/capability/tool/agent/fallback/replan).

## Compatibility fixes (audited, minimal)

- `agents/agent_context.py` was an empty module breaking every
  `agents.*` import: restored the small `set/get/clear` container
  `BaseAgent` requires.
- `AbilityManager.execute(..., capabilities=[...])`: canonical
  capabilities authorized individually at execution (legacy tool-name
  check retained when absent); `ToolMatcher` always passes the step's
  required capabilities, so planning-time denial and execution-time
  denial agree.
