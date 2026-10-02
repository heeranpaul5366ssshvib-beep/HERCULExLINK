from __future__ import annotations
"""HERCULE-LM checkpoint evaluation CLI (N3 §20, levels 1-2).

Usage::

    python -m models.hercule_lm.evaluate --checkpoint <dir> [--arithmetic-n 50]

Level 1 (training health): validation loss + perplexity on the corpus
validation split. Level 2 (language): held-out 3-digit arithmetic
exact-match + generation samples. No HERCULE pipeline here — that is
N3 §20 level 3/4, run separately through the evaluation framework.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import checkpoint as ckpt
from .config import HerculeLMConfig
from .data import DataSource, encode_split, load_documents, split_documents
from .model import HerculeLM
from .tokenizer import HerculeBPETokenizer


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hercule-lm-evaluate")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tokenizer-dir", default="")
    parser.add_argument("--corpus-dir", default="training/data/raw")
    parser.add_argument("--sources", default="training/data/sources.json")
    parser.add_argument("--arithmetic-n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    try:
        manifest = json.loads((Path(args.checkpoint) / "manifest.json").read_text(encoding="utf-8"))
        config = HerculeLMConfig.from_dict(manifest["architecture"])
    except Exception as exc:
        print(f"CHECKPOINT_CORRUPTED: {exc}", file=sys.stderr)
        return 2
    tok_dir = args.tokenizer_dir or f"training/tokenizer/{config.tokenizer_id}"
    try:
        from .hf_tokenizer import load_hf_tokenizer
        try:
            tokenizer = load_hf_tokenizer(tok_dir)
        except Exception:
            tokenizer = HerculeBPETokenizer.load(tok_dir)
    except Exception:
        tokenizer = HerculeBPETokenizer.load(tok_dir)
    model = HerculeLM(config, seed=0)
    try:
        ckpt.load_checkpoint(args.checkpoint, model, strict=True)
    except Exception as exc:
        print(f"CHECKPOINT_MISMATCH: {exc}", file=sys.stderr)
        return 2

    # ---- Level 1: validation health ----
    sources = [DataSource(**s) for s in json.loads(Path(args.sources).read_text(encoding="utf-8"))]
    docs = load_documents(args.corpus_dir, sources, paragraphs=True)
    splits = split_documents(docs)
    seq_len = config.context_length // 2
    stream = encode_split(tokenizer, splits["validation"] or splits["train"], seq_len, seed=args.seed)
    losses: list = []
    accs: list = []
    try:
        from .data import make_batches
        batches = make_batches(stream, seq_len, 4, seed=args.seed)
    except ValueError as exc:
        print(f"NO_DATASET: {exc}", file=sys.stderr)
        return 2
    for xs, ys in batches[:8]:
        logits, cache = model.forward(xs)
        loss, _ = model.loss_and_backward(logits, cache, ys)
        losses.append(loss)
        pred = logits.argmax(axis=-1)
        mask = ys != -100
        accs.append(float(((pred == ys) & mask).sum() / max(1, int(mask.sum()))))
    val_loss = float(sum(losses) / len(losses))
    result = {"checkpoint": args.checkpoint,
              "evaluation": "hercule-lm-eval-v1",
              "level1": {"valid_loss": round(val_loss, 4),
                         "perplexity": round(float(np.exp(min(20.0, val_loss))), 2),
                         "next_token_accuracy": round(float(sum(accs) / len(accs)), 4)}}

    # ---- Level 2: held-out arithmetic (3-digit, never in corpus pairs) ----
    rng = np.random.default_rng(args.seed + 1)
    exact, total = 0, 0
    samples = []
    for _ in range(args.arithmetic_n):
        a, b = int(rng.integers(100, 1000)), int(rng.integers(100, 1000))
        prompt = f"Q: Calculate {a} + {b}.\nA:"
        ids = model.generate(tokenizer.encode(prompt), max_new_tokens=10, temperature=0.0)
        text = tokenizer.decode(ids)
        continuation = text[len(prompt):].strip()
        # Extract the first token/number from the continuation
        # The expected format is "ANSWER." where ANSWER is the sum
        # Use exact match for the full expected answer (including period)
        want = str(a + b) + "."
        # Clean the continuation: take first token/number
        cont = continuation.strip().split()[0] if continuation.strip() else ""
        hit = (cont == want)
        exact += int(hit)
        total += 1
        if len(samples) < 5:
            samples.append({"prompt": prompt, "want": want, "got": continuation[:20], "hit": hit})
    result["level2"] = {"arithmetic_exact": exact, "arithmetic_total": total,
                        "rate": round(exact / max(1, total), 3), "samples": samples}
    print(json.dumps(result, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
