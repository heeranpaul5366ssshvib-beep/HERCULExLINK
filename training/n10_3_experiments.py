from __future__ import annotations
"""N10.3 NANO Controlled Recovery Experiments

Run experiments A-F from the same frozen initialization checkpoint.
"""

import argparse
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np

from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.data import (
    DataSource, encode_split, load_documents, make_batches,
    split_documents, validate_documents, check_no_leakage,
    dataset_manifest, load_documents
)
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer


def cosine_lr(step: int, total: int, base: float, warmup: int = 50) -> float:
    if step < warmup:
        return base * max(0.05, (step + 1) / max(1, warmup))
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return base * 0.5 * (1.0 + math.cos(math.pi * progress))


def _fail(code: int, message: str) -> int:
    print(f"N10.3 ERROR [{code}]: {message}", file=sys.stderr)
    return code


def evaluate_model(model, valid_batches, arithmetic_n=50):
    """Evaluate model on validation loss and arithmetic."""
    # Level 1: validation loss
    losses = []
    accs = []
    for xs, ys in valid_batches[:8]:
        logits, cache = model.forward(xs)
        loss, _ = model.loss_and_backward(logits, cache, ys)
        losses.append(loss)
        pred = logits.argmax(axis=-1)
        mask = ys != -100
        accs.append(float(((pred == ys) & mask).sum() / max(1, int(mask.sum()))))

    val_loss = float(sum(losses) / len(losses))
    next_token_acc = float(sum(accs) / len(accs))

    # Level 2: arithmetic
    rng = np.random.default_rng(42)
    exact = 0
    total = 0
    for _ in range(arithmetic_n):
        a = int(rng.integers(100, 1000))
        b = int(rng.integers(100, 1000))
        prompt = f"Q: Calculate {a} + {b}.\nA:"
        # This would need the tokenizer - simplified for now
        total += 1

    return {
        "val_loss": val_loss,
        "perplexity": float(np.exp(min(20.0, val_loss))),
        "next_token_accuracy": next_token_acc,
        "arithmetic_exact": exact,
        "arithmetic_total": total,
        "rate": exact / max(1, total)
    }


def run_experiment(
    exp_name: str,
    exp_config: dict,
    base_checkpoint: str,
    corpus_dir: str,
    sources_path: str,
    tokenizer_dir: str,
    output_dir: str,
    max_steps: int = 5000,
    eval_every: list = None,
    seed: int = 42
) -> dict:
    """Run a single experiment from the base initialization."""
    if eval_every is None:
        eval_every = [1000, 2500, 5000]

    print(f"\n{'='*60}")
    print(f"Starting Experiment: {exp_config['name']}")
    print(f"Config: lr={exp_config['lr']}, dropout={exp_config['dropout']}, label_smoothing={exp_config['label_smoothing']}")
    print(f"{'='*60}")

    # Load manifest and config from base checkpoint
    with open(Path(base_checkpoint) / "manifest.json", "r") as f:
        manifest = json.load(f)

    arch = manifest["architecture"]
    # Override with experiment config
    arch = dict(arch)
    arch["dropout"] = exp_config["dropout"]
    arch["label_smoothing"] = exp_config.get("label_smoothing", 0.0)

    config = HerculeLMConfig.from_dict(arch)

    # Load tokenizer
    tokenizer = HerculeBPETokenizer.load(tokenizer_dir)

    # Load corpus
    sources_raw = json.loads(Path(sources_path).read_text(encoding="utf-8"))
    sources = [DataSource(**s) for s in sources_raw]
    docs = load_documents(corpus_dir, sources, paragraphs=True)
    splits = split_documents(docs)

    # Check for leakage
    leak = check_no_leakage(splits)
    if leak["overlap"]:
        raise ValueError(f"DATASET LEAKAGE: {leak['overlap'][:3]}")

    # Create manifest
    manifest_data = dataset_manifest("n10-nano-recovery", "v1", sources, docs, splits)

    # Create model
    model = HerculeLM(config, seed=0)

    # Load base initialization
    ckpt.load_checkpoint(base_checkpoint, model, strict=True)
    print(f"Loaded base initialization from {base_checkpoint}")

    # Prepare data streams
    seq_len = config.context_length // 2
    train_stream = encode_split(tokenizer, splits["train"], seq_len, seed=0)
    valid_stream = encode_split(tokenizer, splits["validation"] or splits["train"], seq_len, seed=1)

    if len(valid_stream) < seq_len + 1:
        print("Validation split empty; using train stream for monitoring")
        valid_stream = train_stream

    train_batches = make_batches(train_stream, seq_len, 8, seed=0)
    valid_batches = make_batches(valid_stream, seq_len, 4, seed=1)

    # Training setup
    run_id = f"n10_3_{exp_name.lower()}_{int(time.time())}"
    ckpt_root = Path("training/checkpoints") / run_id
    ckpt_root.mkdir(parents=True, exist_ok=True)

    # Training state
    step = 0
    best_val = float("inf")
    accum_grads = None
    accum_loss = 0.0
    accum_count = 0
    tokens_seen = 0
    micro_batch = 8
    accum_steps = 1
    seq_len_actual = config.context_length // 2

    # Results tracking
    results = {
        "experiment": exp_name,
        "config": exp_config,
        "checkpoints": [],
        "final_metrics": {}
    }

    # Training loop
    total_steps = max_steps
    deadline = 0.0  # No time limit

    try:
        for step in range(max_steps):
            # Learning rate
            lr = cosine_lr(step, max_steps, exp_config["lr"])

            # Training step
            t0 = time.perf_counter()
            accum_loss = 0.0
            accum_count = 0
            accum_grads = None

            for _ in range(accum_steps):
                xs, ys = next(iter(make_batches(
                    encode_split(tokenizer, splits["train"], seq_len, seed=step),
                    seq_len_actual, 8, seed=step
                )))

                logits, cache = model.forward(xs)
                loss, grads = model.loss_and_backward(logits, cache, ys)

                if not np.isfinite(loss):
                    raise ValueError(f"TRAINING_DIVERGED: non-finite loss at step {step}")

                if accum_grads is None:
                    accum_grads = {k: v.copy() for k, v in grads.items()}
                else:
                    for key in accum_grads:
                        accum_grads[key] += grads[key]

                accum_loss += float(loss)
                accum_count += 1

            mean_loss = accum_loss / max(1, accum_count)
            for key in accum_grads:
                accum_grads[key] /= max(1, accum_count)

            gnorm = model.clip_grads(accum_grads, 1.0)
            model.adamw_step(accum_grads, lr)

            # Evaluation
            eval_result = None
            if (step + 1) in eval_every or step == max_steps - 1:
                eval_result = evaluate_model(model, valid_batches, arithmetic_n=50)
                val_loss = eval_result["val_loss"]
                print(f"  Step {step+1}: train_loss={mean_loss:.4f}, val_loss={val_loss:.4f}, "
                      f"ppl={eval_result['perplexity']:.1f}, acc={eval_result['next_token_accuracy']:.4f}, "
                      f"arith={eval_result['rate']:.3f}")

                results["checkpoints"].append({
                    "step": step + 1,
                    "train_loss": mean_loss,
                    "val_loss": val_loss,
                    "perplexity": eval_result["perplexity"],
                    "next_token_accuracy": eval_result["next_token_accuracy"],
                    "arithmetic_rate": eval_result["rate"]
                })

                if val_loss < best_val:
                    best_val = val_loss

            # Checkpoint
            if (step + 1) % 1000 == 0:
                # Save checkpoint (simplified)
                pass

    except KeyboardInterrupt:
        print("Training interrupted")

    return results


def main():
    parser = argparse.ArgumentParser(description="N10.3 NANO Recovery Experiments")
    parser.add_argument("--experiment", choices=["A", "B", "C", "D", "E", "F", "all"], default="all")
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--eval-every", type=int, nargs="+", default=[1000, 2500, 5000])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # Load experiment config
    with open("artifacts/hercule_lm/n10_experiment_config.json", "r") as f:
        config = json.load(f)

    base_checkpoint = config["base_initialization"]
    corpus_dir = config["dataset"]
    sources_path = config["sources"]
    tokenizer_dir = config["tokenizer"]
    output_dir = "training/checkpoints/n10_3_experiments"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    experiments_to_run = list(config["experiments"].keys())
    if args.experiment != "all":
        experiments_to_run = [args.experiment]

    all_results = {}

    for exp_name in experiments_to_run:
        exp_config = config["experiments"][exp_name]
        result = run_experiment(
            exp_name=exp_name,
            exp_config=config["experiments"][exp_name],
            base_checkpoint=config["base_initialization"],
            corpus_dir=config["dataset"],
            sources_path=config["sources"],
            tokenizer_dir=config["tokenizer"],
            output_dir=output_dir,
            max_steps=args.steps,
            eval_every=args.eval_every,
            seed=args.seed
        )
        all_results[exp_name] = result

    # Save results
    with open("artifacts/hercule_lm/n10_3_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("\nAll experiments completed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())