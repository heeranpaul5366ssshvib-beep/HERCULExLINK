# Model Card: hercule-lm-nano

Parameters: 933120
Lineage: hercule-lm random initialization (no pretrained weights)
License: HERCULE-authored (MIT, repo)

## Checkpoint
```json
"UNKNOWN (no checkpoint supplied)"
```
## Benchmarks
see phase6_eval.json
## Safety
see phase6_eval.json SAFETY suite
## Limitations
- from-scratch model; no pretrained capability inherited
- tiny-model baselines score near zero on reasoning suites (measured)
- CUDA/multi-GPU status per frontier reports, not this card
- post-training improvements require measured eval deltas