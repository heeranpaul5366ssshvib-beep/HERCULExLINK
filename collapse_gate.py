#!/usr/bin/env python3
"""Collapse / diversity gate: scan all checkpoints in a run.

For each step_XXXXXXXX dir: read valid_loss from manifest, generate
probes, and report repetition / unique-token / entropy signals.
A collapsing model shows: low unique tokens, high top-1 concentration,
low entropy, repeated substrings (e.g. "000000", "update update").

Usage:
    python collapse_gate.py --run training/checkpoints/100m/run-1790779280 \
        --tokenizer-dir training/tokenizer/hercule-bpe-nano-v1
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np


def repetition_rate(token_ids) -> float:
    """Fraction of 5-grams that appear more than once."""
    ids = list(token_ids)
    if len(ids) < 10:
        return 0.0
    grams = [tuple(ids[i:i + 5]) for i in range(len(ids) - 4)]
    if not grams:
        return 0.0
    counts = Counter(grams)
    repeated = sum(1 for g in grams if counts[g] > 1)
    return repeated / len(grams)


def shannon_entropy(token_ids) -> float:
    ids = list(token_ids)
    if not ids:
        return 0.0
    counts = Counter(ids)
    n = len(ids)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def top1_concentration(token_ids) -> float:
    ids = list(token_ids)
    if not ids:
        return 1.0
    counts = Counter(ids)
    return max(counts.values()) / len(ids)


def longest_repeat_run(token_ids) -> int:
    ids = list(token_ids)
    best = cur = 1
    for i in range(1, len(ids)):
        cur = cur + 1 if ids[i] == ids[i - 1] else 1
        best = max(best, cur)
    return best


def main() -> int:
    parser = argparse.ArgumentParser(prog="collapse-gate")
    parser.add_argument("--run", required=True, help="Run dir with step_* checkpoints")
    parser.add_argument("--tokenizer-dir", default="training/tokenizer/hercule-bpe-nano-v1")
    parser.add_argument("--max-new-tokens", type=int, default=40)
    parser.add_argument("--out", default="", help="JSON report path")
    args = parser.parse_args()

    from models.hercule_lm import checkpoint as ckpt
    from models.hercule_lm.config import HerculeLMConfig
    from models.hercule_lm.model import HerculeLM

    try:
        from models.hercule_lm.hf_tokenizer import load_hf_tokenizer
        tok = load_hf_tokenizer(args.tokenizer_dir)
    except Exception:
        from models.hercule_lm.tokenizer import HerculeBPETokenizer
        tok = HerculeBPETokenizer.load(args.tokenizer_dir)

    probes = [
        "Hello world",
        "Calculate 12 + 8.",
        "The capital of France is",
        "Once upon a time",
        "Write a Python function that adds two numbers.",
    ]

    run_dir = Path(args.run)
    steps = sorted([d for d in run_dir.iterdir()
                    if d.is_dir() and d.name.startswith("step_")])
    if not steps:
        print(f"No step_* checkpoints in {args.run}", file=sys.stderr)
        return 2

    report = {"run": str(run_dir), "checkpoints": []}
    print(f"{'step':>10} {'valid':>8} {'uniq':>6} {'rep5':>6} {'entr':>6} {'top1':>6} {'maxrun':>6}  verdict")
    for step_dir in steps:
        manifest = json.loads((step_dir / "manifest.json").read_text())
        config = HerculeLMConfig.from_dict(manifest["architecture"])
        model = HerculeLM(config, seed=0)
        ckpt.load_checkpoint(str(step_dir), model, strict=True)

        all_ids = []
        for prompt in probes:
            ids = tok.encode(prompt)
            out = model.generate(ids, max_new_tokens=args.max_new_tokens, temperature=0.0)
            all_ids.extend(out)

        uniq = len(set(all_ids))
        rep = repetition_rate(all_ids)
        ent = shannon_entropy(all_ids)
        top1 = top1_concentration(all_ids)
        maxrun = longest_repeat_run(all_ids)
        valid = manifest.get("train_state", {}).get("valid_loss")

        collapsed = (uniq < 20) or (rep > 0.5) or (top1 > 0.8) or (maxrun > 15)
        verdict = "COLLAPSED" if collapsed else "OK"
        valid_s = f"{valid:.4f}" if isinstance(valid, (int, float)) else "n/a"
        print(f"{step_dir.name:>10} {valid_s:>8} {uniq:>6} {rep:>6.3f} "
              f"{ent:>6.2f} {top1:>6.3f} {maxrun:>6}  {verdict}")
        report["checkpoints"].append({
            "step": step_dir.name, "valid_loss": valid,
            "unique_tokens": uniq, "rep5_rate": round(rep, 4),
            "entropy": round(ent, 3), "top1": round(top1, 4),
            "max_repeat_run": maxrun, "verdict": verdict,
        })

    oks = [c for c in report["checkpoints"] if c["verdict"] == "OK"]
    with_valid = [c for c in oks if isinstance(c["valid_loss"], (int, float))]
    if with_valid:
        best = min(with_valid, key=lambda c: c["valid_loss"])
        print(f"\nBest non-collapsed checkpoint: {best['step']} (valid={best['valid_loss']:.4f})")
        report["recommended"] = best["step"]
    else:
        print("\nNo non-collapsed checkpoint with valid loss found.")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1))
        print(f"Report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
