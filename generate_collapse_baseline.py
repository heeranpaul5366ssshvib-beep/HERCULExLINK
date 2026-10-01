"""Generate baseline collapse samples for N10.2 diagnosis."""

from __future__ import annotations

import json
from models.hercule_lm.config import get_preset
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm import checkpoint as ckpt


def main():
    # Load model and tokenizer
    config = get_preset('HERCULE-NANO')
    model = HerculeLM(config, seed=42)
    ckpt.load_checkpoint('training/checkpoints/n10/run-1790433607/step_00002951', model, strict=True)
    tokenizer = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')

    # Load prompts
    with open('artifacts/hercule_lm/n10_nano_collapse_baseline.json', 'r') as f:
        data = json.load(f)

    prompts = data['prompts']

    results = {
        "metadata": {
            "checkpoint": "training/checkpoints/n10/run-1790433607/step_00002951",
            "model": "HERCULE-NANO",
            "steps": 2951,
            "tokens_seen": 188800,
        },
        "samples": []
    }

    def generate(prompt, max_new_tokens=32):
        input_ids = tokenizer.encode(prompt)
        output_ids = model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            temperature=0.0,
            seed=42
        )
        return tokenizer.decode(output_ids)

    # Process each category
    for category, prompt_list in prompts.items():
        print(f"Processing {category}...")
        for i, prompt in enumerate(prompt_list):
            print(f"  {category} {i+1}/{len(prompt_list)}")
            try:
                output = generate(prompt, max_new_tokens=32)
                results['samples'].append({
                    "category": category,
                    "index": i,
                    "prompt": prompt,
                    "output": output,
                    "continuation": output[len(prompt):]
                })
            except Exception as e:
                results['samples'].append({
                    "category": category,
                    "index": i,
                    "prompt": prompt,
                    "output": f"ERROR: {str(e)}",
                    "continuation": ""
                })

    # Save results
    with open('artifacts/hercule_lm/n10_nano_collapse_samples.json', 'w') as f:
        json.dump(results, f, indent=1)

    print(f"Saved {len(results['samples'])} samples to artifacts/hercule_lm/n10_nano_collapse_samples.json")


if __name__ == "__main__":
    main()