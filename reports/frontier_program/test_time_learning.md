# Test-Time Learning (Phase 6U) — IMPLEMENTED + TESTED

**Module:** `cognition/adaptation/` (11 files). Integrates with
MemoryManager, ExperienceManager, SkillManager, Planner, PolicyManager
via dependency injection — **zero Core files modified**.

## Loop

observe → attempt → detect → diagnose (CONFIRMED/LIKELY/UNCERTAIN) →
world-state update (provenance) → strategy revision (never identical
repeat) → policy-gated retry (bounded; escalation needs approval) →
verify → consolidate (CANDIDATE→VALIDATING→VALIDATED→CONSOLIDATED) →
retain → reuse within scope.

## Measured (synthetic harness)

- A/B: baseline 0.0 → adaptive 1.0 success (verdict: adaptive-better)
- Acceptance demo (11 steps): fail → diagnose → revise → retry →
  verify → retain → reuse; unrelated tasks unaffected
- Mistake recovery rate: 1.0; repeated-failure tracking active

## Safety invariants (tested)

- No weight/code/policy/permission modification (nothing imports them)
- TASK scope default; cross-user isolation; expiry; contradiction flags
- Failed hypotheses never promoted; skills proposed, never auto-installed
- Offline export contains recovered traces only (feeds Phase-6 SFT later)

## Tests

22/22 green in `tests/test_adaptation.py` (all 16 spec categories +
acceptance). Full suite: see regression below.
