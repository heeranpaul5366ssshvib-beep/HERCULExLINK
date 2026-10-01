# LearningManager._knowledge silo — role, duplication, migration plan

## Current role

`cognition/learning/learning_manager.py` defines `LearningEngine`, a
plain in-memory key/value store (`learn/recall/update/forget/all/
clear` over `_knowledge: dict`). Audit (Phase F + G): **zero
production callers**. It is referenced only by
`cognition/ownership.py` as a declared component name. The live
`Brain.learning` attribute is a different class
(`brain/learning_engine.py: LearningEngine`).

## Duplication analysis

| Store | API | Owner |
|---|---|---|
| `LearningEngine._knowledge` | KV learn/recall | nobody (orphan) |
| `SemanticMemory` | KV learn/recall/forget | `MemoryManager` |
| `KnowledgeManager` | docs/ontology/vectors | knowledge/ |
| `ExperienceManager` | validated task outcomes | cognition/experience/ |

The orphan duplicates `SemanticMemory` (same shape, no wiring) and
partially overlaps `ExperienceManager` (which adds validation,
provenance-by-task, and procedure promotion).

## Migration plan (next phase, NOT this change)

1. Freeze: no new callers of `cognition.learning...LearningEngine`.
2. Adapter: implement `learn/recall` as a thin facade over
   `ExperienceManager.query/record` for the `general` goal type, behind
   a feature flag; run both, compare.
3. Ownership: move the "learning" row in `ownership.py` to
   `cognition.experience.experience_manager.ExperienceManager`.
4. Remove the dict store once no test/reference remains.

No migration was performed in Phase G to avoid destabilizing the
verified foundation for an unused path.
