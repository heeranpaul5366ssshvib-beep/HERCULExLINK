#!/usr/bin/env python
"""CHECKPOINT 3: CURRENT A GENERATION AUDIT"""

import json
import os
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM
from models.hercule_lm import checkpoint as ckpt

eval_prompts = {
    'natural_language': [
        'What is the capital of France?',
        'Explain photosynthesis in one sentence.',
        'Who wrote Romeo and Juliet?',
        'What is the largest planet?',
        'Describe the water cycle.',
        'What is the speed of light?',
        'Who painted the Mona Lisa?',
        'What is democracy?',
        'Explain gravity simply.',
        'What causes seasons?',
        'Define photosynthesis.',
        'What is DNA?',
        'How do vaccines work?',
        'What is a black hole?',
        'Explain evolution briefly.',
        'What is the periodic table?',
        'How does the internet work?',
        'What is machine learning?',
        'Describe the solar system.',
        'What is quantum physics?',
    ],
    'arithmetic': [
        'What is 2 + 2?',
        'What is 15 - 7?',
        'What is 6 * 7?',
        'What is 48 / 6?',
        'Calculate 15 + 27.',
        'What is 100 - 34?',
        'Multiply 8 * 9.',
        'Divide 144 by 12.',
        'What is 12 * 12?',
        'What is 50 - 18?',
    ],
    'structured_reasoning': [
        'If all cats are mammals and all mammals are animals, are cats animals?',
        'If it rains, the ground gets wet. The ground is wet. Did it rain?',
        'All birds can fly. Penguins are birds. Can penguins fly?',
        'If A implies B and B implies C, does A imply C?',
        'Some dogs are brown. All brown things are cute. Are some dogs cute?',
        'If x > 5 and x < 10, what integer values can x be?',
        'A > B, B > C. Is A > C?',
        'Not (A and B) is equivalent to what?',
        'If P then Q. Not Q. What follows?',
        'All squares are rectangles. Are all rectangles squares?',
    ],
    'tool_call': [
        'Use calculator to compute 25 * 4.',
        'Use calculator to add 123 + 456.',
        'Calculate the square root of 144.',
        'What is 2 to the power of 10?',
        'Compute 15 * 15.',
        'What is the factorial of 5?',
        'Calculate 2^8.',
        'What is 100 / 4?',
        'Multiply 7 * 8 * 9.',
        'What is 1000 - 1?',
    ],
    'arc_style': [
        'Transform: input grid 2x2 all zeros, output grid 2x2 all ones.',
        'Pattern: 1 2 3 -> 2 3 4. Apply to 5 6 7.',
        'Grid 3x3: rotate 90 degrees clockwise.',
        'Input: 1 0 1 / 0 1 0 / 1 0 1. Output: invert colors.',
        'Sequence: 2, 4, 8, 16. Next?',
        'Grid: mirror horizontally.',
        'Pattern: A B A B A B. Next?',
        'Grid 2x2: swap diagonals.',
        'Pattern: 1, 1, 2, 3, 5, 8. Next?',
        'Grid: transpose.',
    ]
}

checkpoint_path = r'C:\Users\hp\HERCULE\training\checkpoints\n10\run-1790519157\step_00005557'

with open(os.path.join(checkpoint_path, 'manifest.json'), 'r') as f:
    manifest = json.load(f)

from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM
from models.hercule_lm import checkpoint as ckpt

config = HerculeLMConfig.from_dict(manifest['architecture'])
tokenizer = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')
model = HerculeLM(config, seed=0)
ckpt.load_checkpoint(r'C:\Users\hp\HERCULE\training\checkpoints\n10\run-1790519157\step_00005557', model, strict=True)

results = []
for category, prompts in eval_prompts.items():
    for prompt in prompts:
        tokens = tokenizer.encode(prompt)
        result = model.generate(tokens, max_new_tokens=20, temperature=0.0, seed=42)
        gen_tokens = result[len(tokens):]
        gen_text = tokenizer.decode(gen_tokens)
        
        result = {
            'category': category,
            'prompt': prompt,
            'tokenized_prompt': tokens,
            'generated_tokens': gen_tokens,
            'decoded_generation': gen_text,
            'generation_length': len(gen_tokens),
        }
        results.append(result)

with open('artifacts/hercule_lm/n10_3_a_capability_audit.json', 'w') as f:
    json.dump(results, f, indent=2)

print('Audit saved. Total prompts:', len(results))

# Quick summary
by_cat = {}
for r in results:
    cat = r['category']
    if cat not in by_cat:
        by_cat[cat] = {'total': 0, 'empty': 0, 'zeros': 0}
    by_cat[cat]['total'] += 1
    if not r['decoded_generation'].strip():
        by_cat[cat]['empty'] += 1
    if r['decoded_generation'].strip().startswith('0'):
        by_cat[cat]['zeros'] += 1

print('\n=== SUMMARY ===')
for cat, stats in by_cat.items():
    print(f"{cat}: {stats['total']} prompts, {stats['empty']} empty, {stats['zeros']} starting with '0'")