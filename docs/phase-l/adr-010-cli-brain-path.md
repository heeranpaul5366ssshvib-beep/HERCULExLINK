# ADR-010 — All executable CLI requests use Brain.run_cycle

Date: 2026-09-05 · Status: accepted

## Context

`boot.py` called `ModelManager.generate(user_input)` directly (with a
fabricating fallback), bypassing tasks, policy, verification, tracing,
and memory — reducing ModelManager to a top-level oracle.

## Decision

The CLI initializes via `RuntimeInitializer` and routes every line
through `HerculeCli`: questions to `brain.think`, everything
executable to `Brain.run_cycle`. `UniversalFallbackManager` raises
instead of inventing answers. No second init system, no CLI planning.

## Consequences

- Every CLI execution is a durable, policy-checked, verified task.
- Tests drive `handle_line` deterministically with test doubles; no
  external services required.
