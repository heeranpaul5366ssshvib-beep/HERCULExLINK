# N8 Experiment Design

Fixed: micro (3,088,384 params), frozen micro tokenizer, seed 0,
AdamW lr 3e-4 cosine, batch 8×64, 150 steps (76,800 tokens), clip 1.0.
Only the corpus varies. Checkpoints under `training/n8/checkpoints/`;
baseline `training/checkpoints/micro1` untouched.

| ID | Corpus | Docs | Rationale |
|---|---|---|---|
| A | hercule-seed-v1 | 6,450 | reproducibility control |
| B | seed_unique | 3,266 | repetition removed |
| C | expanded | 6,621 | +3,355 authored docs |
| D | controlled_2x | 6,532 | exact 2x cap |
| E | arithmetic | 6,326 | arithmetic-heavy + 10% mixed |

Cross-evaluation grounds (identical procedure for all): seed-val
stream, N7 30-item set, 30-item held-out arithmetic. Own-val splits
are reported but not compared across corpora (different distributions).
