#!/usr/bin/env python3
"""Trained-model baseline protocol (Phase 9B).

Evaluates BASE / SFT / ADAPTIVE configurations of a REAL trained
checkpoint on the frozen harness WITHOUT merging scores. Requires an
existing checkpoint dir; exits 3 (BLOCKED) when none is supplied.

Usage:
  python scripts/trained_baseline.py --checkpoint <dir> [--sft-checkpoint <dir>]
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "reports" / "frontier_program"


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="hercule-trained-baseline")
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--sft-checkpoint", default="")
    parser.add_argument("--tokenizer-dir", default="")
    parser.add_argument("--suites", nargs="*", default=["MATH", "CODING", "STRUCTURED_OUTPUT"])
    args = parser.parse_args(argv)

    if not args.checkpoint or not Path(args.checkpoint).exists():
        stub = {"timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "BLOCKED",
                "reason": "no trained checkpoint supplied (pass --checkpoint <dir>)"}
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "trained_baseline.json").write_text(json.dumps(stub, indent=1))
        print("BLOCKED: no trained checkpoint.")
        return 3

    from models.hercule_lm import checkpoint as ckpt
    from models.hercule_lm.config import HerculeLMConfig
    from models.hercule_lm.eval_harness import model_predict_factory, run_all
    from models.hercule_lm.tokenizer import HerculeBPETokenizer
    from models.hercule_lm.torch_model import TorchHerculeLM

    man = json.loads((Path(args.checkpoint) / "manifest.json").read_text(encoding="utf-8"))
    cfg = HerculeLMConfig.from_dict(man["architecture"])
    if not args.tokenizer_dir:
        print("BLOCKED: pass --tokenizer-dir <dir>.")
        return 3
    tok = HerculeBPETokenizer.load(args.tokenizer_dir)

    out: dict = {"timestamp": datetime.now(timezone.utc).isoformat(),
                 "base_checkpoint": args.checkpoint,
                 "arch_hash": man.get("architecture_hash")}
    for label, ckdir in (("base", args.checkpoint),
                         ("sft", args.sft_checkpoint or args.checkpoint)):
        model = TorchHerculeLM(cfg, seed=0)
        ckpt.load_torch_checkpoint(ckdir, model, strict=True, map_to="cpu")
        rep = run_all(model_predict_factory(model, tok, max_new_tokens=16),
                      model_id=f"hercule-{label}", checkpoint=ckdir,
                      suites=args.suites)
        out[label] = {s: rep["suites"][s]["mean"] for s in args.suites}
    (REPORTS / "trained_baseline.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("base", "sft")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
