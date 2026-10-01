from __future__ import annotations
"""Run the N7 eval set against a checkpoint (N7.13): deterministic.

Usage::

    python -m training.n7.run_eval --checkpoint <dir> --out training/n7/eval_results_micro1.json

Scoring rules operate on the greedy continuation only: prefix,
contains, exact-after-strip. Stores input/expected/generated/score/
metadata per item — never hidden reasoning (there is none; the
model emits continuations).
"""

import argparse
import json
import time
from pathlib import Path

from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer


def score_item(item: dict, continuation: str) -> bool:
    rule = item.get("rule", "contains")
    if rule == "prefix":
        return continuation.strip().lower().startswith(str(item.get("expected_prefix", "")).lower())
    if rule == "exact-after-strip":
        return continuation.strip() == str(item.get("expected_exact", ""))
    return str(item.get("expected_prefix", "")).lower() in continuation.lower()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="n7-run-eval")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tokenizer-dir", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--max-new-tokens", type=int, default=12)
    args = parser.parse_args(argv)
    base = Path(__file__).resolve().parent
    items = json.loads((base / "eval_set.json").read_text(encoding="utf-8"))
    manifest = json.loads((base / "eval_manifest.json").read_text(encoding="utf-8"))
    ck_manifest = json.loads((Path(args.checkpoint) / "manifest.json").read_text(encoding="utf-8"))
    config = HerculeLMConfig.from_dict(ck_manifest["architecture"])
    tok_dir = args.tokenizer_dir or f"training/tokenizer/{config.tokenizer_id}"
    tokenizer = HerculeBPETokenizer.load(tok_dir)
    model = HerculeLM(config, seed=0)
    ckpt.load_checkpoint(args.checkpoint, model, strict=True)
    results = []
    t0 = time.perf_counter()
    for item in items:
        ids = tokenizer.encode(item["prompt"])
        try:
            out = model.generate(ids, max_new_tokens=args.max_new_tokens, temperature=0.0)
            continuation = tokenizer.decode(out)[len(item["prompt"]):]
            hit = score_item(item, continuation)
            error = ""
        except Exception as exc:
            continuation, hit, error = "", False, f"{type(exc).__name__}: {exc}"[:160]
        results.append({"id": item["id"], "category": item["category"],
                        "prompt": item["prompt"], "expected": item.get("expected_prefix",
                                        item.get("expected_exact", "")),
                        "generated": continuation[:200], "hit": hit, "error": error})
    elapsed = time.perf_counter() - t0
    payload = {"checkpoint": args.checkpoint,
               "model_id": ck_manifest.get("model_id", ""),
               "eval_version": manifest["version"],
               "eval_checksum": manifest["checksum"],
               "items": len(results),
               "hits": sum(1 for r in results if r["hit"]),
               "elapsed_s": round(elapsed, 1),
               "results": results}
    print(json.dumps({k: v for k, v in payload.items() if k != "results"}, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
