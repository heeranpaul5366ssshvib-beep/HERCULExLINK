from __future__ import annotations
"""HERCULE-LM text generation CLI (N3 §15): checkpoint → text.

Usage::

    python -m models.hercule_lm.generate --checkpoint training/checkpoints/<run>/step_00000200 --prompt "Q: Calculate 317 + 542."
"""

import argparse
import sys
import time
from pathlib import Path

from . import checkpoint as ckpt
from .config import HerculeLMConfig
from .model import HerculeLM
from .tokenizer import HerculeBPETokenizer


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hercule-lm-generate")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tokenizer-dir", default="")
    parser.add_argument("--prompt", default="Q: Calculate 317 + 542.\nA:")
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        manifest = __import__("json").loads(
            (Path(args.checkpoint) / "manifest.json").read_text(encoding="utf-8"))
        config = HerculeLMConfig.from_dict(manifest["architecture"])
    except Exception as exc:
        print(f"CHECKPOINT_CORRUPTED: {exc}", file=sys.stderr)
        return 2
    tok_dir = args.tokenizer_dir or f"training/tokenizer/{config.tokenizer_id}"
    try:
        tokenizer = HerculeBPETokenizer.load(tok_dir)
    except Exception as exc:
        print(f"TOKENIZER_FAILURE: {exc}", file=sys.stderr)
        return 2
    model = HerculeLM(config, seed=0)
    try:
        ckpt.load_checkpoint(args.checkpoint, model, strict=True)
    except Exception as exc:
        print(f"CHECKPOINT_MISMATCH: {exc}", file=sys.stderr)
        return 2
    start_ids = tokenizer.encode(args.prompt)
    t0 = time.perf_counter()
    try:
        out_ids = model.generate(start_ids, max_new_tokens=args.max_new_tokens,
                                 temperature=args.temperature, seed=args.seed)
    except Exception as exc:
        print(f"INFERENCE_FAILURE: {exc}", file=sys.stderr)
        return 3
    elapsed = time.perf_counter() - t0
    text = tokenizer.decode(out_ids)
    print(text)
    print(f"[ids={len(out_ids)} new={len(out_ids) - len(start_ids)} "
          f"{elapsed * 1000:.0f}ms]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
