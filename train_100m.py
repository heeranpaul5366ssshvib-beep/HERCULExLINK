#!/usr/bin/env python3
"""Train HERCULE-100M model (N10.4 scale).

Usage:
    python train_100m.py --steps 5000 --batch 16 --seq-len 512
    python train_100m.py --resume training/checkpoints/100m/run-xxx/step_0001000 --steps 5000
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from models.hercule_lm.config import HerculeLMConfig, load_config
from models.hercule_lm.model import HerculeLM
from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.hf_tokenizer import load_hf_tokenizer
from models.hercule_lm.data import (DataSource, load_documents, validate_documents,
                                     split_documents, check_no_leakage, dataset_manifest,
                                     encode_split, cached_stream, make_batches)


def cosine_lr(step: int, total: int, base: float, warmup: int = 100) -> float:
    if step < warmup:
        return base * max(0.01, (step + 1) / max(1, warmup))
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return base * 0.5 * (1.0 + np.cos(np.pi * progress))


def main():
    parser = argparse.ArgumentParser(prog="hercule-100m-train")
    parser.add_argument("--config", default="hercule_lm_100m", help="Model config name")
    parser.add_argument("--corpus-dir", default="training/data/large_corpus", help="Corpus directory")
    parser.add_argument("--sources", default="training/data/large_corpus/sources.json", help="Sources JSON")
    parser.add_argument("--tokenizer-dir", default="training/tokenizer/hercule-bpe-100m-v2-fast", help="Tokenizer directory")
    parser.add_argument("--checkpoint-root", default="training/checkpoints/100m", help="Checkpoint root")
    parser.add_argument("--run-id", default="", help="Run ID (default: timestamp)")
    parser.add_argument("--steps", type=int, default=5000, help="Training steps")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--micro-batch", type=int, default=0, help="Micro batch size (default: batch)")
    parser.add_argument("--grad-accum", type=int, default=1, help="Gradient accumulation steps")
    parser.add_argument("--seq-len", type=int, default=512, help="Sequence length")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--resume", default="", help="Resume from checkpoint")
    parser.add_argument("--eval-every", type=int, default=500, help="Evaluation interval")
    parser.add_argument("--ckpt-every", type=int, default=1000, help="Checkpoint interval")
    parser.add_argument("--max-secs", type=float, default=0.0, help="Max training time (0 = unlimited)")
    parser.add_argument("--metrics-log", default="", help="Metrics log file")
    parser.add_argument("--device", default="cpu", help="cpu | cuda | cuda:N")
    parser.add_argument("--backend", default="auto", help="auto | numpy | torch")
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    print(f"Config: {config.model_id}, params: {config.parameter_count():,}, vocab: {config.vocab_size}")
    
    # Load tokenizer
    print(f"Loading tokenizer from {args.tokenizer_dir}...")
    try:
        from models.hercule_lm.hf_tokenizer import load_hf_tokenizer
        tokenizer = load_hf_tokenizer(args.tokenizer_dir)
    except Exception:
        from models.hercule_lm.tokenizer import HerculeBPETokenizer
        tokenizer = HerculeBPETokenizer.load(args.tokenizer_dir)
    print(f"Tokenizer: vocab_size={tokenizer.vocab_size}")
    
    # Load corpus
    print(f"Loading corpus from {args.corpus_dir}...")
    sources_raw = json.loads(Path(args.sources).read_text())
    sources = [DataSource(**s) for s in sources_raw]
    docs = load_documents(args.corpus_dir, sources, paragraphs=True)
    validate_documents(docs, ["HERCULE-authored (MIT, repo)"])
    splits = split_documents(docs)
    leak = check_no_leakage(splits)
    if leak["overlap"]:
        print(f"DATASET LEAKAGE: {leak['overlap'][:3]}", file=sys.stderr)
        return 2
    manifest = dataset_manifest("hercule-100m", "v1", sources, docs, splits)
    print(f"Dataset: {manifest['documents']} docs, hash={manifest['dataset_hash'][:16]}")
    print(f"Splits: {leak['sizes']}")
    
    # Create model
    run_id = args.run_id or f"run-{int(time.time())}"
    ckpt_root = Path(args.checkpoint_root) / run_id
    model = HerculeLM(config, seed=args.seed)
    start_step = 0
    resumed_state = {}
    
    if args.resume:
        print(f"Resuming from {args.resume}...")
        resumed_manifest = ckpt.load_checkpoint(args.resume, model, strict=True)
        start_step = model._step_count
        resumed_state = dict(resumed_manifest.get("train_state", {}) or {})
        print(f"Resumed at step {start_step}")
    
    print(f"Model params: {model.parameter_count():,}")
    
    # Prepare data streams
    cache_dir = str(Path("training") / "streams")
    train_stream = cached_stream(tokenizer, splits["train"], args.seq_len,
                                 seed=args.seed, cache_dir=cache_dir,
                                 corpus_hash=manifest["dataset_hash"] + ":train")
    valid_stream = cached_stream(tokenizer, splits["validation"], args.seq_len,
                                 seed=args.seed, cache_dir=cache_dir,
                                 corpus_hash=manifest["dataset_hash"] + ":valid")
    
    if len(valid_stream) < args.seq_len + 1:
        print("Validation split empty; using train stream for monitoring")
        valid_stream = train_stream
    
    print(f"Train tokens: {len(train_stream):,}, Valid tokens: {len(valid_stream):,}")
    
    # Create batches
    micro_batch = int(args.micro_batch or args.batch)
    accum_steps = max(1, int(args.grad_accum or 1))
    effective_batch = micro_batch * accum_steps
    
    train_batches = make_batches(train_stream, args.seq_len, micro_batch, seed=args.seed)
    valid_batches = make_batches(valid_stream, args.seq_len, max(1, micro_batch // 2), seed=args.seed + 1)
    
    print(f"Train batches: {len(train_batches)}, Valid batches: {len(valid_batches)}")
    print(f"Effective batch size: {effective_batch} (micro={micro_batch} x accum={accum_steps})")
    
    # Training loop
    train_state = {"step": start_step}
    best_val = float("inf")
    deadline = time.perf_counter() + args.max_secs if args.max_secs > 0 else 0.0
    interrupted = False
    total_steps = start_step + args.steps
    tokens_seen = int(resumed_state.get("tokens_seen", 0))
    accum_grads = None
    accum_loss, accum_count = 0.0, 0
    micro_index = int(resumed_state.get("micro_index", start_step * accum_steps))
    
    try:
        for step in range(start_step, total_steps):
            if deadline and time.perf_counter() > deadline:
                print("Time budget reached; checkpointing and stopping", flush=True)
                break
            
            lr = cosine_lr(step, total_steps, args.lr)
            t0 = time.perf_counter()
            
            for _ in range(accum_steps):
                xs, ys = train_batches[micro_index % len(train_batches)]
                micro_index += 1
                
                try:
                    logits, cache = model.forward(xs)
                    loss, grads = model.loss_and_backward(logits, cache, ys)
                except MemoryError:
                    print("OUT_OF_MEMORY: reduce batch/seq-len", file=sys.stderr)
                    return 3
                
                if not np.isfinite(loss):
                    print(f"TRAINING_DIVERGED: non-finite loss at step {step}", file=sys.stderr)
                    return 3
                
                if accum_grads is None:
                    accum_grads = {k: v.copy() for k, v in grads.items()}
                else:
                    for key in accum_grads:
                        accum_grads[key] += grads[key]
                accum_loss += float(loss)
                accum_count += 1
                tokens_seen += int(xs.size)
            
            mean_loss = accum_loss / max(1, accum_count)
            for key in accum_grads:
                accum_grads[key] /= max(1, accum_count)
            gnorm = model.clip_grads(accum_grads, 1.0)
            model.adamw_step(accum_grads, lr)
            accum_grads, accum_loss, accum_count = None, 0.0, 0
            
            dt = time.perf_counter() - t0
            eff_tokens = micro_batch * args.seq_len * accum_steps
            step_num = step + 1
            
            train_state.update({
                "step": step_num, "lr": lr, "loss": float(mean_loss),
                "grad_norm": float(gnorm), "micro_index": micro_index,
                "tokens_seen": tokens_seen
            })
            
            if args.metrics_log:
                with open(args.metrics_log, "a") as f:
                    f.write(json.dumps({
                        "step": step_num, "tokens": tokens_seen,
                        "loss": round(float(mean_loss), 4),
                        "lr": lr, "grad_norm": round(float(gnorm), 3),
                        "tok_s": round(eff_tokens / max(dt, 1e-6), 1)
                    }) + "\n")
            
            if step_num % 10 == 0 or step_num == start_step + 1:
                print(f"step={step_num}/{total_steps} loss={mean_loss:.4f} lr={lr:.2e} "
                      f"gnorm={gnorm:.2f} {dt*1000:.0f}ms {eff_tokens/max(dt,1e-6):.0f}tok/s", flush=True)
            
            if step_num % args.eval_every == 0:
                val_losses = []
                for xs, ys in valid_batches[:8]:
                    logits, cache = model.forward(xs)
                    loss, _ = model.loss_and_backward(logits, cache, ys)
                    val_losses.append(loss)
                val_loss = float(np.mean(val_losses))
                ppl = float(np.exp(min(20.0, val_loss)))
                print(f"  valid loss={val_loss:.4f} ppl={ppl:.1f}", flush=True)
                train_state["valid_loss"] = val_loss
                best_val = min(best_val, val_loss)
            
            if step_num % args.ckpt_every == 0:
                target = ckpt_root / f"step_{step_num:08d}"
                ckpt.save_checkpoint(str(target), model, tokenizer.manifest(), manifest,
                                     dict(train_state), {
                                         "run_id": run_id, "config": config.as_dict(),
                                         "seed": args.seed, "optimizer": "adamw",
                                         "scheduler": "cosine", "lr": args.lr,
                                         "batch": args.batch, "seq_len": args.seq_len,
                                         "steps": args.steps
                                     })
                print(f"  Checkpoint saved: {target}", flush=True)
    
    except KeyboardInterrupt:
        interrupted = True
        print("INTERRUPTED by user; saving latest state", flush=True)
    
    # Final save
    final_step = train_state.get("step", start_step)
    target = ckpt_root / f"step_{final_step:08d}"
    ckpt.save_checkpoint(str(target), model, tokenizer.manifest(), manifest,
                         dict(train_state), {
                             "run_id": run_id, "config": config.as_dict(),
                             "seed": args.seed, "optimizer": "adamw",
                             "scheduler": "cosine", "lr": args.lr,
                             "batch": args.batch, "seq_len": args.seq_len,
                             "steps": args.steps
                         })
    ckpt.write_latest(str(Path(args.checkpoint_root)), str(ckpt_root))
    print(f"Done: steps={final_step} best_valid={best_val:.4f} tokens={tokens_seen} root={ckpt_root}")
    
    return 130 if interrupted else 0


if __name__ == "__main__":
    sys.exit(main())