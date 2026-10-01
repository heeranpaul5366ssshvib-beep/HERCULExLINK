# Learning Architecture (Phase H)

## Audit verdict

`LearningEngine._knowledge` was **dead state + duplicated knowledge +
legacy implementation**: zero production callers, same KV shape as
`SemanticMemory`, partial overlap with `ExperienceManager`, and no
consumer of any "learned" content. Not an incomplete feature — nothing
reads it.

## Responsibilities (final)

- KNOWLEDGE → `KnowledgeManager` (reference material + provenance)
- MEMORY → `MemoryManager` (interaction state)
- EXPERIENCE → `ExperienceManager` (distilled, queryable outcomes)
- LEARNING → `LearningEngine` (evaluated intake → proposals →
  validation → promotion; **stores no knowledge**)

## Pipeline

`ingest_evaluated(experience, quality)` accepts only evaluated input
(success + verification + quality score present) and returns a receipt;
anything else is refused with a reason. `propose` /  
`propose_from_experiences` build typed proposals (procedure,
retrieval, routing, workflow, knowledge candidates) with sources,
rationale, expected benefit, confidence, and validation requirements —
sources must be ingested first. `validate` enforces support /
mean-success / quality thresholds (defaults 2 / 0.7 / 0.5, preserving
the "meaningful evidence" rule); `promote` requires VALIDATED status
plus an approver; `reject` records reasons; PROMOTED is final.
`to_contract()` maps records onto the ownership `LearningProposal`
contract (`accepted` mirrors promotion).

## Orphan removal

`_knowledge` is deleted. `learn/recall/update/forget/all/clear` raise
`RuntimeError` with a migration pointer instead of failing with a bare
`AttributeError`. No hidden store remains; `statistics()` reports
intake/proposal counts by status. All proposal/promotion/rejection
decisions trace via `trace_learning` on the `learning` stage.
