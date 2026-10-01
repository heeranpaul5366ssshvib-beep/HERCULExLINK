from __future__ import annotations
"""Master training orchestrator (frontier P36): safe command surface.

Usage::

    python -m training.run --model hercule-lm-100m --dry-run
    python -m training.run --model hercule-lm-micro --dataset seed --steps 100

--dry-run validates architecture/dataset/tokenizer/hardware/state
and prints READY or BLOCKED without training. Real runs delegate to
models.hercule_lm.train with recorded manifests. Never launches a
run the hardware gate rejects.
"""

import argparse
import json
import sys
from pathlib import Path

from models.hercule_lm.config import load_config
from models.hercule_lm.estimate import estimate_memory, estimate_time, memory_for_config

DATASETS = {
    "seed": ("training/data/raw", "training/data/sources.json"),
    "instruct": ("training/data/instruct", "training/data/instruct/sources.json"),
}


def _cmd(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hercule-training-run")
    parser.add_argument("--model", default="hercule-lm-micro")
    parser.add_argument("--dataset", default="seed")
    parser.add_argument("--config", default="")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--backend", default="auto")
    parser.add_argument("--dtype", default="float32")
    parser.add_argument("--amp", default="off")
    parser.add_argument("--resume", default="")
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--micro-batch", type=int, default=0)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--seq-len", type=int, default=0)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--max-secs", type=float, default=0.0)
    parser.add_argument("--target-tokens", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        wanted = (args.config or args.model).replace("-", "_")
        config = load_config(wanted)
    except Exception as exc:
        print(f"BLOCKED: MODEL_CONFIG_INVALID: {exc}")
        return 2
    if args.dataset not in DATASETS:
        print(f"BLOCKED: unknown dataset {args.dataset!r} (known: {sorted(DATASETS)})")
        return 2
    corpus_dir, sources_path = DATASETS[args.dataset]
    from models.hercule_lm.device import get_training_device

    try:
        device = get_training_device(args.device)
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    if not device.available:
        print(f"BLOCKED: device {device.device} unavailable")
        return 2

    seq_len = int(args.seq_len or config.context_length // 2)
    mem = memory_for_config(config, args.batch, seq_len)
    ckpt_mb = mem["checkpoint_memory_mb"] + mem["model_memory_mb"]
    tok_s = _known_throughput(config.model_id)
    report = {
        "model": config.model_id, "parameters": config.parameter_count(),
        "dataset": args.dataset, "device": device.as_dict(),
        "memory_estimate_mb": mem, "checkpoint_mb": round(ckpt_mb, 1),
        "tokens_per_sec": tok_s if tok_s else "NOT MEASURED for this config",
    }
    if args.target_tokens > 0 and tok_s:
        from models.hercule_lm.estimate import estimate_time as _eta

        report["time_estimate"] = _eta(tok_s, args.target_tokens)
    print(json.dumps(report, indent=1))
    if args.dry_run:
        ok = _dry_checks(config, corpus_dir, sources_path, device, tok_s, mem,
                         seq_len, args.batch)
        print("READY" if ok else "BLOCKED")
        return 0 if ok else 2
    # Real run: delegate with recorded provenance. The requested
    # device/backend must reach the trainer (a dropped --device here
    # previously forced every run onto the NumPy CPU path).
    from models.hercule_lm.train import main as train_main

    train_args = ["--config", args.config or args.model, "--corpus-dir", corpus_dir,
                  "--sources", sources_path, "--steps", str(args.steps),
                  "--batch", str(args.batch), "--seq-len", str(seq_len),
                  "--device", str(args.device), "--backend", str(args.backend),
                  "--dtype", str(args.dtype), "--amp", str(args.amp),
                  "--micro-batch", str(args.micro_batch),
                  "--grad-accum", str(args.grad_accum),
                  "--lr", str(args.lr), "--seed", str(args.seed),
                  "--max-secs", str(args.max_secs)]
    if args.resume:
        train_args += ["--resume", args.resume]
    if args.run_id:
        train_args += ["--run-id", args.run_id]
    return int(train_main(train_args))


def _known_throughput(model_id: str):
    table = {"hercule-lm-nano": 784.0, "hercule-lm-micro": 292.0,
             "hercule-lm-s10m": 87.6, "hercule-lm-s25m": 46.7,
             "hercule-lm-s50m": 27.9, "hercule-lm-100m": 16.7}
    return table.get(model_id)


def _dry_checks(config, corpus_dir: str, sources_path: str, device, tok_s,
                mem, seq_len: int, batch: int) -> bool:
    ok = True
    try:
        config.validate()
        print(f"architecture: OK ({config.parameter_count()} params)")
    except Exception as exc:
        print(f"architecture: FAIL {exc}")
        ok = False
    try:
        from models.hercule_lm.data import (load_documents, split_documents,
                                            validate_documents, DataSource)

        sources = [DataSource(**s) for s in
                   json.loads(Path(sources_path).read_text(encoding="utf-8"))]
        docs = load_documents(corpus_dir, sources, paragraphs=True)
        validate_documents(docs, ["HERCULE-authored (MIT, repo)"])
        print(f"dataset: OK ({len(docs)} docs)")
    except Exception as exc:
        print(f"dataset: FAIL {exc}")
        ok = False
    try:
        from training.n6.hardware_gate import evaluate_gate
        from training.n6.hardware_gate import audit_hardware

        hardware = audit_hardware()
        chinchilla = config.parameter_count() * 20
        verdict = evaluate_gate(
            hardware, target_tokens=chinchilla, max_days=30.0,
            measured_tok_s=float(tok_s or 0.0),
            measured_peak_mb=float(mem["total_training_mb"]),
            measured_free_mb=float(hardware.get("ram_free_mb", 0.0) or 0.0),
            min_free_mb=float(mem["total_training_mb"] * 1.5 + 1000.0),
            needs_accelerator=config.parameter_count() >= 50_000_000)
        print(f"hardware gate: {verdict['status']} (target {chinchilla:_} tokens)")
        if verdict["status"] != "READY":
            print(f"hardware gate reason: {verdict.get('reason', '')}")
            return False
    except Exception as exc:
        print(f"hardware gate: FAIL {exc}")
        ok = False
    try:
        from system.state_guard import describe_isolation

        print(f"state isolation: {describe_isolation()}")
    except Exception as exc:
        print(f"state isolation: FAIL {exc}")
        ok = False
    print(f"device: {device.device} ({device.backend})")
    return ok


def main(argv=None) -> int:
    return _cmd(argv)


if __name__ == "__main__":
    raise SystemExit(main())
