from __future__ import annotations
"""HERCULE-LM training loop (N9): real gradient descent with curriculum.

CLI::

    python -m models.hercule_lm.train --config HERCULE-NANO --steps 200
    python -m models.hercule_lm.train --config HERCULE-NANO --curriculum --steps 2500
    python -m models.hercule_lm.train --resume training/checkpoints/<run>/step_000200

Survives Ctrl+C (saves + exits 130). Checkpoints are atomic; resume
validates identity. Exit codes: 0 ok, 2 bad config/data, 3 OOM-ish
resource failure, 130 interrupted.
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

from .threads import configure_threads as _configure_threads

_configure_threads()  # must precede numpy import to affect BLAS threading

import numpy as np

from . import checkpoint as ckpt
from .config import HerculeLMConfig, load_config
from .curriculum import CurriculumManager, DEFAULT_CURRICULUM, create_curriculum_schedule
from .data import (check_no_leakage, dataset_manifest, encode_split,
                   load_documents, make_batches, split_documents,
                   validate_documents, DataSource)
from .model import HerculeLM
from .tokenizer import HerculeBPETokenizer


def cosine_lr(step: int, total: int, base: float, warmup: int = 50) -> float:
    if step < warmup:
        return base * max(0.05, (step + 1) / max(1, warmup))
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return base * 0.5 * (1.0 + math.cos(math.pi * progress))


def _fail(code: int, message: str) -> int:
    print(f"HERCULE-LM ERROR [{code}]: {message}", file=sys.stderr)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hercule-lm-train")
    parser.add_argument("--config", default="hercule_lm_nano")
    parser.add_argument("--corpus-dir", default="training/data/raw")
    parser.add_argument("--sources", default="training/data/sources.json")
    parser.add_argument("--tokenizer-dir", default="")
    parser.add_argument("--checkpoint-root", default="training/checkpoints")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--micro-batch", type=int, default=0)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--seq-len", type=int, default=0)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--resume", default="")
    parser.add_argument("--eval-every", type=int, default=50)
    parser.add_argument("--ckpt-every", type=int, default=100)
    parser.add_argument("--max-secs", type=float, default=0.0)
    parser.add_argument("--metrics-log", default="")
    parser.add_argument("--sft-marker", default="")
    parser.add_argument("--curriculum", action="store_true",
                        help="Enable N9 curriculum learning (staged domains)")
    parser.add_argument("--curriculum-stages", default="",
                        help="Comma-separated stage names to run (default: all)")
    parser.add_argument("--device", default="cpu",
                        help="cpu | cuda | cuda:N | auto "
                             "(cuda requests never fall back silently)")
    parser.add_argument("--backend", default="auto",
                        help="auto | numpy | torch "
                             "(auto: cuda-request->torch, cpu->numpy)")
    parser.add_argument("--dtype", default="float32",
                        help="float32 (FP32 first; other dtypes need --amp)")
    parser.add_argument("--amp", default="off",
                        help="off | fp16 | bf16 (torch backend only)")
    parser.add_argument("--allowed-licenses", nargs="*", default=[
        "HERCULE-authored (MIT, repo)"])
    return parser


def resolve_backend(args) -> str:
    """Pick 'numpy' or 'torch' without silent fallback.

    --device cpu        => numpy (reference)
    --device cuda|cu:N  => torch (fails clearly when CUDA is missing)
    --device auto       => torch when CUDA is probed, else numpy
    --backend numpy|torch overrides auto-selection explicitly; a
    contradictory pair (numpy+cuda) fails instead of guessing.
    """
    backend = str(getattr(args, "backend", "auto") or "auto").strip().lower()
    device = str(getattr(args, "device", "cpu") or "cpu").strip().lower()
    if backend not in ("auto", "numpy", "torch"):
        raise ValueError(f"invalid --backend {backend!r} (expected auto|numpy|torch)")
    if backend == "numpy":
        if device == "cpu" or device == "auto":
            return "numpy"
        raise ValueError(f"backend 'numpy' is CPU-only; got --device {device!r} "
                         f"(use --backend torch for CUDA)")
    if backend == "torch":
        return "torch"
    # backend == auto
    if device == "cpu":
        return "numpy"
    if device == "auto":
        from .device import _torch_info

        info = _torch_info()
        return "torch" if bool(info and info["cuda"]) else "numpy"
    if device == "cuda" or device.startswith("cuda:"):
        return "torch"
    raise ValueError(f"invalid --device {device!r} (expected cpu|cuda|cuda:N|auto)")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        selected = resolve_backend(args)
    except ValueError as exc:
        return _fail(2, str(exc))
    if selected == "torch":
        # Real PyTorch path (CPU or CUDA, per --device; CUDA requests
        # fail clearly inside the torch runner when unavailable).
        if str(getattr(args, "device", "")).strip().lower() == "auto":
            args.device = "cpu"  # explicit torch backend + auto => torch CPU
        from .train_torch import run_from_namespace as _run_torch

        return int(_run_torch(args))

    try:
        config = load_config(args.config)
    except Exception as exc:
        return _fail(2, f"MODEL_CONFIG_INVALID: {exc}")
    seq_len = int(args.seq_len or config.context_length // 2)
    if seq_len >= config.context_length:
        return _fail(2, "MODEL_CONFIG_INVALID: seq_len must be < context_length")

    # ---- corpus ----
    try:
        sources_raw = json.loads(Path(args.sources).read_text(encoding="utf-8"))
        sources = [DataSource(**s) for s in sources_raw]
        docs = load_documents(args.corpus_dir, sources, paragraphs=True)
    except Exception as exc:
        return _fail(2, f"NO_DATASET: {exc}")
    try:
        validate_documents(docs, args.allowed_licenses)
    except ValueError as exc:
        return _fail(2, str(exc))
    splits = split_documents(docs)
    leak = check_no_leakage(splits)
    if leak["overlap"]:
        return _fail(2, f"DATASET LEAKAGE: {leak['overlap'][:3]}")
    manifest = dataset_manifest("hercule-seed", "v1", sources, docs, splits)
    print(f"dataset docs={manifest['documents']} hash={manifest['dataset_hash']} "
          f"splits={leak['sizes']}", flush=True)

    # ---- tokenizer (cached by dataset hash; retrains only on change) ----
    tok_dir = args.tokenizer_dir or f"training/tokenizer/{config.tokenizer_id}"
    tok_hash_path = Path(tok_dir) / ".corpus_hash"
    tok_current_hash = manifest["dataset_hash"]
    if (Path(tok_dir) / "tokenizer.json").exists() and tok_hash_path.exists() \
            and tok_hash_path.read_text(encoding="utf-8").strip() == tok_current_hash:
        from .tokenizer import HerculeBPETokenizer as _Tok

        tokenizer = _Tok.load(tok_dir)
        print(f"tokenizer reused from cache ({tok_dir})", flush=True)
    else:
        from .tokenizer import HerculeBPETokenizer as _Tok

        train_texts = [d.text for d in splits["train"]]
        tokenizer = _Tok.train(
            train_texts, vocab_size=config.vocab_size, corpus_version="hercule-seed-v1")
        tokenizer.save(tok_dir)
        tok_hash_path.write_text(tok_current_hash, encoding="utf-8")
    print(f"tokenizer vocab={tokenizer.vocab_size} merges={len(tokenizer.merges)} "
          f"checksum={tokenizer.checksum()}", flush=True)

    # ---- model ----
    run_id = args.run_id or f"run-{int(time.time())}"
    ckpt_root = Path(args.checkpoint_root) / run_id
    model = HerculeLM(config, seed=args.seed)
    start_step = 0
    resumed_state: dict = {}
    if args.resume:
        try:
            resumed_manifest = ckpt.load_checkpoint(args.resume, model, strict=True)
            start_step = model._step_count
            resumed_state = dict(resumed_manifest.get("train_state", {}) or {})
            print(f"resumed from {args.resume} at step {start_step}", flush=True)
        except Exception as exc:
            return _fail(2, f"CHECKPOINT_MISMATCH/CORRUPTED: {exc}")
    print(f"model={config.model_id} params={model.parameter_count()} "
          f"seed={args.seed} arch={config.architecture_hash()}", flush=True)

    run_manifest = {
        "run_id": run_id, "config": config.as_dict(), "seed": args.seed,
        "python": platform.python_version() if (platform := __import__("platform")) else "?",
        "numpy": np.__version__, "torch": None,
        "optimizer": "adamw", "scheduler": "cosine", "lr": args.lr,
        "batch": args.batch, "seq_len": seq_len, "steps": args.steps,
        "hardware": {"cpu": platform.processor() or platform.machine(),
                     "os": f"{platform.system()} {platform.release()}"},
    }
    # N5 §8: gradient accumulation. micro_batch defaults to batch;
    # effective = micro × accum × devices(devices=1, single-device only).
    micro_batch = int(args.micro_batch or args.batch)
    accum_steps = max(1, int(args.grad_accum or 1))
    num_devices = 1
    effective_batch = micro_batch * accum_steps * num_devices
    run_manifest.update({
        "micro_batch_size": micro_batch,
        "gradient_accumulation_steps": accum_steps,
        "effective_batch_size": effective_batch,
        "number_of_devices": num_devices,
        "device": "cpu", "backend": "numpy", "dtype": "float32",
        "amp": "disabled (no torch backend here)",
    })

    from .data import cached_stream

    cache_dir = str(Path("training") / "streams")
    train_stream = cached_stream(tokenizer, splits["train"], seq_len,
                                 seed=args.seed, cache_dir=cache_dir,
                                 corpus_hash=manifest["dataset_hash"] + ":train")
    valid_stream = cached_stream(tokenizer, splits["validation"], seq_len,
                                 seed=args.seed, cache_dir=cache_dir,
                                 corpus_hash=manifest["dataset_hash"] + ":valid")
    if len(valid_stream) < seq_len + 1:
        # Tiny corpora can hash-skew into an empty validation split;
        # fall back to the train stream for health monitoring only
        # (reported honestly; never used for model selection here).
        print("validation split empty; monitoring train stream instead", flush=True)
        valid_stream = train_stream
    print(f"train_tokens={len(train_stream)} valid_tokens={len(valid_stream)}", flush=True)
    micro_batches = make_batches(train_stream, seq_len, micro_batch, seed=args.seed)
    sft_marker_ids: list = []
    if str(args.sft_marker or ""):
        from .data import mask_before_marker as _mask  # noqa (re-export check)

        sft_marker_ids = tokenizer.encode(str(args.sft_marker))
        print(f"sft masking after marker ids={sft_marker_ids}", flush=True)
    try:
        valid_batches = make_batches(valid_stream, seq_len, max(1, micro_batch // 2),
                                     seed=args.seed + 1)
    except ValueError as exc:
        return _fail(2, str(exc))
    # Formal manifests (N5 §13/§14): standalone auditable run + dataset files.
    _write_manifests(ckpt_root, run_manifest, manifest)

    sft_marker_ids: list = []
    if str(args.sft_marker or ""):
        from .data import mask_before_marker as _mask  # noqa (re-export check)
        sft_marker_ids = tokenizer.encode(str(args.sft_marker))
        print(f"sft masking after marker ids={sft_marker_ids}", flush=True)

    # ---- curriculum or standard training ----
    if args.curriculum:
        return _run_curriculum(args, config, tokenizer, model, ckpt_root, run_manifest,
                               start_step, resumed_state, seq_len, micro_batch, accum_steps,
                               args.batch, valid_stream, splits, manifest, sft_marker_ids)
    else:
        return _run_standard(args, config, tokenizer, model, ckpt_root, run_manifest,
                             start_step, resumed_state, seq_len, micro_batch, accum_steps,
                             micro_batches, valid_batches, sft_marker_ids, manifest)


def _run_curriculum(
    args, config, tokenizer, model, ckpt_root, run_manifest,
    start_step, resumed_state, seq_len, micro_batch, accum_steps,
    batch_size, valid_stream, splits, manifest, sft_marker_ids
) -> int:
    """Run training with N9 curriculum learning."""
    # Initialize curriculum manager
    curriculum_mgr = CurriculumManager(
        config, tokenizer, seed=args.seed,
        corpus_dir=args.corpus_dir, sources_path=args.sources
    )
    
    # Parse stage order if specified
    stage_order = None
    if args.curriculum_stages:
        stage_order = [s.strip() for s in args.curriculum_stages.split(",")]
    
    # Create step schedule
    schedule = create_curriculum_schedule(args.steps)
    print(f"Curriculum schedule: {schedule}")
    
    # Validation batches (use standard validation stream)
    valid_batches = make_batches(valid_stream, seq_len, max(1, micro_batch // 2), seed=args.seed + 1)
    
    train_state = {"step": start_step}
    best_val = float("inf")
    deadline = time.perf_counter() + args.max_secs if args.max_secs > 0 else 0.0
    interrupted = False
    total_steps = start_step + args.steps
    tokens_seen = int(resumed_state.get("tokens_seen", 0))
    accum_grads = None
    accum_loss, accum_count = 0.0, 0
    
    # Create iterators for each stage
    stage_iterators = {}
    stage_steps_remaining = {name: steps for name, steps in schedule}
    
    step = start_step
    try:
        while step < total_steps:
            if deadline and time.perf_counter() > deadline:
                print("time budget reached; checkpointing and stopping", flush=True)
                break
            
            # Determine current stage
            current_stage = None
            for stage_name, remaining in stage_steps_remaining.items():
                if remaining > 0:
                    current_stage = stage_name
                    break
            
            if current_stage is None:
                print("All curriculum stages completed", flush=True)
                break
            
            # Initialize iterator for this stage if needed
            if current_stage not in stage_iterators:
                stage_obj = next(s for s in DEFAULT_CURRICULUM if s.name == current_stage)
                stage_iterators[current_stage] = curriculum_mgr.curriculum_iterator(
                    batch_size=batch_size, micro_batch=micro_batch, seq_len=seq_len,
                    stage_order=[current_stage]
                )
            
            # Get next batch from current stage
            try:
                stage_name, (xs, ys) = next(stage_iterators[current_stage])
            except StopIteration:
                # Stage exhausted, move to next
                stage_steps_remaining[current_stage] = 0
                continue
            
            lr = cosine_lr(step, total_steps, args.lr)
            t0 = time.perf_counter()
            
            for _ in range(accum_steps):
                if sft_marker_ids:
                    from .data import mask_before_marker
                    ys = mask_before_marker(ys, sft_marker_ids)
                try:
                    logits, cache = model.forward(xs)
                    loss, grads = model.loss_and_backward(logits, cache, ys)
                except MemoryError:
                    return _fail(3, "OUT_OF_MEMORY: batch does not fit; reduce --batch/--seq-len")
                if not np.isfinite(loss):
                    return _fail(3, f"TRAINING_DIVERGED: non-finite loss at step {step}")
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
            eff_tokens = micro_batch * seq_len * accum_steps
            step += 1
            stage_steps_remaining[current_stage] -= 1
            
            train_state.update({"step": step, "lr": lr, "loss": float(mean_loss),
                                "grad_norm": float(gnorm),
                                "tokens_seen": tokens_seen,
                                "curriculum_stage": current_stage})
            
            if args.metrics_log:
                import json as _json
                with open(args.metrics_log, "a", encoding="utf-8") as handle:
                    handle.write(_json.dumps({
                        "step": step, "tokens": tokens_seen,
                        "loss": round(float(mean_loss), 4),
                        "valid_loss": round(float(train_state.get("valid_loss", 0.0) or 0.0), 4),
                        "lr": lr, "grad_norm": round(float(gnorm), 3),
                        "tok_s": round(eff_tokens / max(dt, 1e-6), 1),
                        "stage": current_stage}) + "\n")
            
            if step % 10 == 0 or step == start_step + 1:
                print(f"step={step}/{total_steps} stage={current_stage} "
                      f"loss={mean_loss:.4f} lr={lr:.2e} gnorm={gnorm:.2f} "
                      f"{dt * 1000:.0f}ms {eff_tokens / max(dt, 1e-6):.0f}tok/s "
                      f"(micro={micro_batch}x{accum_steps})", flush=True)
            
            if step % args.eval_every == 0:
                val_loss = _evaluate(model, valid_batches)
                ppl = float(np.exp(min(20.0, val_loss)))
                print(f"  valid loss={val_loss:.4f} ppl={ppl:.1f}", flush=True)
                train_state["valid_loss"] = float(val_loss)
                best_val = min(best_val, val_loss)
            
            if step % args.ckpt_every == 0:
                _save(ckpt_root, step, model, tokenizer, manifest, train_state, run_manifest)
                
    except KeyboardInterrupt:
        interrupted = True
        print("TRAINING_INTERRUPTED by user; saving latest state", flush=True)
    
    _save(ckpt_root, train_state.get("step", start_step), model,
          tokenizer, manifest, train_state, run_manifest)
    ckpt.write_latest(str(Path(args.checkpoint_root)), str(ckpt_root))
    print(f"done steps={train_state.get('step')} best_valid={best_val:.4f} "
          f"tokens={tokens_seen} root={ckpt_root}", flush=True)
    return 130 if interrupted else 0


def _run_standard(
    args, config, tokenizer, model, ckpt_root, run_manifest,
    start_step, resumed_state, seq_len, micro_batch, accum_steps,
    micro_batches, valid_batches, sft_marker_ids, dataset_manifest
) -> int:
    """Run standard (non-curriculum) training."""
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
                print("time budget reached; checkpointing and stopping", flush=True)
                break
            lr = cosine_lr(step, total_steps, args.lr)
            t0 = time.perf_counter()
            for _ in range(accum_steps):
                xs, ys = micro_batches[micro_index % len(micro_batches)]
                micro_index += 1
                if sft_marker_ids:
                    from .data import mask_before_marker
                    ys = mask_before_marker(ys, sft_marker_ids)
                try:
                    logits, cache = model.forward(xs)
                    loss, grads = model.loss_and_backward(logits, cache, ys)
                except MemoryError:
                    return _fail(3, "OUT_OF_MEMORY: batch does not fit; reduce --batch/--seq-len")
                if not np.isfinite(loss):
                    return _fail(3, f"TRAINING_DIVERGED: non-finite loss at step {step}")
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
            eff_tokens = micro_batch * seq_len * accum_steps
            train_state.update({"step": step + 1, "lr": lr, "loss": float(mean_loss),
                                "grad_norm": float(gnorm),
                                "micro_index": micro_index,
                                "tokens_seen": tokens_seen})
            if args.metrics_log:
                import json as _json
                with open(args.metrics_log, "a", encoding="utf-8") as handle:
                    handle.write(_json.dumps({
                        "step": step + 1, "tokens": tokens_seen,
                        "loss": round(float(mean_loss), 4),
                        "valid_loss": round(float(train_state.get("valid_loss", 0.0) or 0.0), 4),
                        "lr": lr, "grad_norm": round(float(gnorm), 3),
                        "tok_s": round(eff_tokens / max(dt, 1e-6), 1),
                        "micro_index": micro_index}) + "\n")
            if (step + 1) % 10 == 0 or step == start_step:
                print(f"step={step + 1}/{total_steps} loss={mean_loss:.4f} "
                      f"lr={lr:.2e} gnorm={gnorm:.2f} {dt * 1000:.0f}ms "
                      f"{eff_tokens / max(dt, 1e-6):.0f}tok/s "
                      f"(micro={micro_batch}x{accum_steps})", flush=True)
            if (step + 1) % args.eval_every == 0:
                val_loss = _evaluate(model, valid_batches)
                ppl = float(np.exp(min(20.0, val_loss)))
                print(f"  valid loss={val_loss:.4f} ppl={ppl:.1f}", flush=True)
                train_state["valid_loss"] = float(val_loss)
                best_val = min(best_val, val_loss)
            if (step + 1) % args.ckpt_every == 0:
                _save(ckpt_root, step + 1, model, tokenizer, dataset_manifest, train_state, run_manifest)
    except KeyboardInterrupt:
        interrupted = True
        print("TRAINING_INTERRUPTED by user; saving latest state", flush=True)
    _save(ckpt_root, train_state.get("step", start_step), model,
          tokenizer, dataset_manifest, train_state, run_manifest)
    ckpt.write_latest(str(Path(args.checkpoint_root)), str(ckpt_root))
    print(f"done steps={train_state.get('step')} best_valid={best_val:.4f} "
          f"tokens={tokens_seen} root={ckpt_root}", flush=True)
    return 130 if interrupted else 0


def _write_manifests(ckpt_root, run_manifest: dict, dataset_manifest: dict) -> None:
    """Standalone auditable run + dataset manifests (N5 §13/§14)."""
    import json as _json

    root = Path(ckpt_root)
    root.mkdir(parents=True, exist_ok=True)
    enriched = dict(run_manifest)
    enriched["rng"] = {"python": "3.14 (random module unused by loop)",
                       "numpy": np.__version__,
                       "streams": "default_rng(seed); CPU-deterministic under "
                                  "fixed seed + batch order; CUDA trajectories "
                                  "are NOT claimed bit-identical"}
    (root / "run_manifest.json").write_text(_json.dumps(enriched, indent=1),
                                            encoding="utf-8")
    (root / "dataset_manifest.json").write_text(_json.dumps(dataset_manifest, indent=1),
                                                encoding="utf-8")


def _evaluate(model: HerculeLM, batches) -> float:
    losses = []
    for xs, ys in batches[:8]:
        logits, cache = model.forward(xs)
        loss, _ = model.loss_and_backward(logits, cache, ys)
        losses.append(loss)
    return float(sum(losses) / max(1, len(losses)))


def _save(ckpt_root: Path, step: int, model, tokenizer, manifest, train_state, run_manifest) -> None:
    target = ckpt_root / f"step_{step:08d}"
    ckpt.save_checkpoint(str(target), model, tokenizer.manifest(), manifest,
                         dict(train_state), dict(run_manifest))


if __name__ == "__main__":
    raise SystemExit(main())
