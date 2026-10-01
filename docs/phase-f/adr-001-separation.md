# ADR-001 — Knowledge / Memory / Experience separation

Date: 2026-09-05 · Status: accepted

## Context

The repo had five overlapping KV knowledge/memory silos
(`SemanticMemory`, `KnowledgeManager`, `LearningManager._knowledge`,
`AgentMemory`, `Orchestrator.Agent.context`) and no experience store;
`Intelligence.experience` was an int counter.

## Decision

Three explicit owners:

- KNOWLEDGE (`knowledge/`): world/reference material + provenance.
- MEMORY (`memory/`): authorized interaction/context retention.
- EXPERIENCE (`cognition/experience/`): distilled, queryable task
  outcomes derived read-only from TaskManager history.

## Consequences

- Retrieval, context, and evaluation consume all three through narrow
  interfaces; no concept is forced into a single store.
- `LearningManager._knowledge` remains untouched (deprecated by
  non-use, not rewritten); future work can migrate it onto
  `ExperienceManager`.
