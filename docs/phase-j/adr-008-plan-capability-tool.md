# ADR-008 — Plan → Capability → Tool binding

Date: 2026-09-05 · Status: accepted

## Context

The planner emitted bare `{step, goal, description}` dicts while
`contracts.PlanStep` (frozen) already described capabilities,
verification, and permissions — so nothing connected plans to the 17
registered abilities, and execution bypassed policy per canonical
capability (tool-name strings like `FILES` instead of `FILE_READ`).

## Decision

- Canonical `Capability` enum + deterministic keyword inference
  (auditable, no LLM strings) enrich steps via the additive
  `Planner.create_capable_plan`; legacy output unchanged.
- `CapabilityRegistry` maps capabilities to validated tool/agent
  providers with live health; `ToolMatcher` ranks (coverage/health/
  reliability) and executes with classified fallback, keeping
  ModelRouter→model / ToolMatcher→tool / AgentManager→agent /
  Orchestrator→coordination strictly separate.
- `AbilityManager.execute` accepts declared canonical `capabilities`
  and authorizes each; the matcher always supplies the step's
  requirements, unifying planning-time and execution-time denial.
- `AutonomousLoop` closes goal→verification→replan through one
  validated path with durable task persistence and full trace stages.

## Consequences

- Invalid plans (missing/unknown/unavailable capabilities, cycles,
  permission conflicts, missing verification) fail before execution.
- Partial coverage forces decomposition or explicit opt-in, never
  silent partial execution; destructive steps never blindly retry.
