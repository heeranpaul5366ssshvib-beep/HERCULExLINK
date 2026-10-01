#!/usr/bin/env python
"""CHECKPOINT 8: TRAINING/VALIDATION MISMATCH ANALYSIS"""

import json

print("=== CHECKPOINT 8: TRAINING/VALIDATION MISMATCH ANALYSIS ===")

with open("training/data/fixed/pipeline_report.json", "r") as f:
    report = json.load(f)

final = report["final_stats"]
print("Training data:")
print("  Tokens: " + format(final["total_tokens"], ","))
print("  Documents: " + format(final["total_documents"], ","))
print("  Vocab coverage: {:.1%}".format(final["vocab_coverage"]))
print("  Whitespace ratio: {:.1%}".format(final["whitespace_ratio"]))

print()
print("=== ANALYSIS ===")
print("The model achieves low validation loss (0.76) by:")
print("  1. Predicting frequent tokens (0, whitespace, common patterns)")
print("  2. Memorizing local n-gram statistics")
print("  3. The validation set likely contains similar patterns to training")
print()
print("But capability requires:")
print("  1. Instruction following (not just next-token prediction)")
print("  2. Compositional reasoning")
print("  3. Arithmetic computation")
print("  4. Structured output formatting")
print()
print("The training objective (next-token prediction) is MISALIGNED with capability.")
print("The model minimizes cross-entropy by predicting high-frequency tokens.")
print("The training data lacks sufficient instruction-following examples.")
print()
print("Evidence:")
print("  - Training data: 934K tokens, but mostly synthetic arithmetic/facts")
print("  - No instruction-following format in training data")
print("  - Model learns to predict '0' and whitespace (high frequency)")
print("  - No instruction-tuning or RLHF stage")