# ARC Evaluation Policy (Phase 9H)

## Current state: NO ARC-AGI DATA VENDORED

- `ARC_STYLE` suite tasks are HERCULE-synthesized grids. They are
  never labeled ARC-AGI-1/2/3 and their scores are never compared
  with official ARC results.
- No ARC-AGI task content is present in training, SFT, or eval data.

## Conditions for real ARC integration

1. Obtain tasks only through the currently valid official ARC-AGI
   distribution channel and follow its current rules exactly.
2. Vendoring evaluation tasks requires a contamination firewall:
   eval hashes registered BEFORE any training run; `verify_disjoint`
   must pass or training is refused.
3. Record per result: benchmark version, harness commit, model,
   checkpoint, inference settings, tool state, attempt policy,
   score, latency, failures.
4. Never compare harnesses with different attempt policies.

## Status: POLICY-ONLY (no ARC-AGI runs)
