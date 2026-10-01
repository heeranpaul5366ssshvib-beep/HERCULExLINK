# Phase 12 Training Report — Scale Generalization

## Arms (same curriculum, same held-out, same eval)

| Arm | Params | Steps | Tokens | Loss | Held-out numeric | Format |
|---|---|---|---|---|---|---|
| A micro-200 (Ph11) | 3.1M | 200 | 51K | 6.98→0.54 | 0/20 | 20/20 |
| B micro-600 (3× duration) | 3.1M | 600 | 154K | 6.98→0.44 | 0/20 | 20/20 |
| C s10m-200 (3× scale) | 10.6M | 200 | 26K | 7.39→0.61 | 0/20 | 20/20 |
| D 100M-CUDA | 100M | — | — | BLOCKED (0 GPUs) | NOT_RUN | NOT_RUN |

## Answers

1. Did 100M change accuracy? **NOT_RUN** (hardware-blocked).
2. Did more tokens change accuracy? **No** — 3× duration, identical 0/20.
3. Failure mode changed? **No** — lookup-table persists (neighbors emitted).
4. Sequences? 0/20 both (Phase 11, unchanged design).
5. Changed: loss floors, format adherence. Not changed: held-out numeric.
6. Smallest justified next step: **GPU + 100M + 10–100× tokens** on this
   frozen curriculum (tests capacity + volume together; duration and 3×
   scale already ruled out at this regime).
