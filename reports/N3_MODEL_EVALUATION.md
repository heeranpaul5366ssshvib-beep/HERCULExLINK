# N3 Model Evaluation

## Random control vs trained (identical suites, N3 §23)

| Checkpoint | Valid loss | Perplexity | Held-out arithmetic (30) |
|---|---|---|---|
| random (seed 999, 0 steps) | 7.1063 | 1219.63 | 0/30 |
| micro1 (291 steps) | 1.532 | 4.63 | 0/30 |

Training demonstrably changed the model (level-1 metrics). Task-level
arithmetic is 0/30 for both — reported honestly; the model learns
answer shapes ("NNN.") before arithmetic at this scale. No
capability improvement is claimed.

## Framework integration subset (hercule-lm-micro bound as default)

uai-core-math-001/002, route-019, memory-017: 4/4 passed. Per §21
attribution: these pass via deterministic HERCULE components
(DETERMINISTIC routing, memory probes, classifier) with zero model
contribution at this capability level — recorded as plumbing proof,
not model intelligence.

## Generation samples (micro1, greedy)

- "Q: Calculate 840 + 953." → "101." (wrong; shape-only learning).
- Smoke nano reload/generate path verified working.

## HERCULE integration status

Provider contract integrated and tested (router registration →
`ModelManager.generate` → provider text; Brain routing pending
further training — the model cannot yet propose usable tool calls,
so full-pipeline integration would fail honestly and is deferred).
Policy/verification/skill/safety layers untouched and authoritative.
