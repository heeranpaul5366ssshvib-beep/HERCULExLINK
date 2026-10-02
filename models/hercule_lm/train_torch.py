from __future__ import annotations
"""HERCULE-LM torch-backend training loop: real PyTorch/CUDA, FP32 first.

Same data/tokenizer pipeline, same hyperparameters semantics, and same
provenance gates as the NumPy reference loop in :mod:`models.hercule_lm.train`:

- gradient accumulation with identical effective-batch semantics
  (mean of per-micro-batch mean gradients)
- cosine LR schedule with warmup (shared ``cosine_lr``)
- AdamW (decoupled, beta1=0.9, beta2=0.999, eps=1e-8, wd=0.01)
- gradient clipping at global norm 1.0
- validation, checkpoint interval, JSONL metrics, max-seconds stop,
  resume from checkpoint (model + optimizer + step + data cursor +
  torch RNG where practical)
- deterministic seeding where practical (CPU trajectories reproduce
  under fixed seed+order; CUDA trajectories are NOT claimed
  bit-identical across hardware)

FP32 is the default and only auto-selected dtype. ``--amp fp16|bf16``
is separately selectable and separately recorded; no speedup is
claimed until measured. Multi-GPU is NOT implemented (single device
only, reported honestly).
"""

import argparse
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

from . import checkpoint as ckpt
from .config import HerculeLMConfig, load_config
from .data import (check_no_leakage, dataset_manifest, load_documents,
                   make_batches, split_documents, validate_documents,
                   DataSource)
from .device import collect_runtime, get_training_device, gpu_utilization
from .distributed import (average_object, barrier, cleanup as _dist_cleanup,
                          ddp_status, get_rank, get_world_size, init_process_group,
                          is_main, log_main, shard_batches, wants_distributed)
from .torch_model import TorchHerculeLM


def cosine_lr(step: int, total: int, base: float, warmup: int = 50) -> float:
    from .train import cosine_lr as _shared

    return _shared(step, total, base, warmup)


def _fail(code: int, message: str) -> int:
    print(f"HERCULE-LM ERROR [{code}]: {message}", file=sys.stderr)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hercule-lm-train-torch")
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
    parser.add_argument("--device", default="cuda",
                        help="cpu | cuda | cuda:N (no silent fallback)")
    parser.add_argument("--dtype", default="float32",
                        help="float32 (only auto-supported dtype today)")
    parser.add_argument("--amp", default="off",
                        help="off | fp16 | bf16 (separately selectable)")
    parser.add_argument("--allowed-licenses", nargs="*", default=[
        "HERCULE-authored (MIT, repo)"])
    return parser


class _TorchDevice:
    """Resolved torch execution device (backend is always torch here)."""

    def __init__(self, device: str, available: bool, name: str = "", count: int = 0):
        self.backend = "torch"
        self.device = device
        self.available = available
        self.name = name
        self.count = count


def _resolve_device(requested: str) -> _TorchDevice:
    """Resolve without fallback: a CUDA request on a CUDA-less box raises.

    ``cpu`` means torch-CPU (``get_training_device("cpu")`` describes the
    NumPy reference instead, so it is not used for this branch).
    """
    want = str(requested or "auto").strip().lower()
    if want == "cpu":
        return _TorchDevice(device="cpu", available=True,
                            name="CPU (torch backend)", count=1)
    probed = get_training_device(want)  # raises clearly when CUDA is missing
    if not probed.available:
        raise RuntimeError(f"device {probed.device} unavailable")
    if probed.backend != "torch":
        # "auto" on a CUDA-less box: torch-CPU, explicitly (never NumPy
        # masquerading as torch).
        return _TorchDevice(device="cpu", available=True,
                            name="CPU (torch backend)", count=1)
    return _TorchDevice(device=probed.device, available=True,
                        name=probed.name, count=probed.count)


def _amp_context(amp: str, device_str: str):
    import torch

    if amp == "fp16":
        return torch.amp.autocast(device_type="cuda" if device_str.startswith("cuda") else "cpu",
                                  dtype=torch.float16)
    if amp == "bf16":
        return torch.amp.autocast(device_type="cuda" if device_str.startswith("cuda") else "cpu",
                                  dtype=torch.bfloat16)
    from contextlib import nullcontext

    return nullcontext()


def run_from_namespace(args, config: HerculeLMConfig | None = None) -> int:
    import torch

    t_start = time.perf_counter()
    try:
        cfg = config or load_config(args.config)
    except Exception as exc:
        return _fail(2, f"MODEL_CONFIG_INVALID: {exc}")
    seq_len = int(args.seq_len or cfg.context_length // 2)
    if seq_len >= cfg.context_length:
        return _fail(2, "MODEL_CONFIG_INVALID: seq_len must be < context_length")

    amp = str(getattr(args, "amp", "off") or "off").strip().lower()
    if amp not in ("off", "fp16", "bf16"):
        return _fail(2, f"MODEL_CONFIG_INVALID: --amp must be off|fp16|bf16 (got {amp!r})")
    dtype_s = str(getattr(args, "dtype", "float32") or "float32").strip().lower()
    if dtype_s != "float32" and amp == "off":
        # Compute stays FP32 unless AMP is explicitly selected.
        return _fail(2, f"MODEL_CONFIG_INVALID: --dtype {dtype_s!r} requires --amp selection "
                        "(FP32 first; fp16/bf16 only via explicit --amp)")

    # ---- device (explicit; never silent fallback) ----
    try:
        dev_info = _resolve_device(getattr(args, "device", "cuda"))
    except RuntimeError as exc:
        return _fail(2, f"DEVICE_UNAVAILABLE: {exc}")
    device_str = dev_info.device
    if not dev_info.available:
        return _fail(2, f"DEVICE_UNAVAILABLE: device {device_str} unavailable")
    if dev_info.backend != "torch":
        return _fail(2, f"DEVICE_UNAVAILABLE: torch backend required for this path "
                         f"(resolved backend={dev_info.backend})")
    torch_device = torch.device(device_str if device_str != "cuda" else "cuda:0"
                                if dev_info.count else "cuda")
    if amp == "fp16" and not str(torch_device).startswith("cuda"):
        return _fail(2, "MODEL_CONFIG_INVALID: --amp fp16 requires a CUDA device "
                        "(CPU fp16 autocast is unsupported here; use --amp bf16 or off)")

    # ---- distributed (explicit; torchrun env only, never faked) ----
    dist_info: dict = {"world_size": 1, "rank": 0, "local_rank": 0,
                       "backend": "none", "distributed": "OFF (single process)"}
    if wants_distributed():
        try:
            dist_info = init_process_group(str(torch_device))
        except RuntimeError as exc:
            return _fail(2, str(exc))
        torch_device = torch.device(dist_info["device"])
        if dist_info["backend"] == "nccl" and amp == "off":
            pass  # FP32 DDP; AMP only via explicit --amp (unchanged rule)
    world_size = int(dist_info.get("world_size", 1))

    # ---- deterministic seeding where practical ----
    seed = int(args.seed)
    random.seed(seed)
    np.random.seed(seed % (2 ** 32))
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    try:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except Exception:
        pass

    # ---- corpus (shared pipeline; never rewritten) ----
    try:
        import json as _json

        sources_raw = _json.loads(Path(args.sources).read_text(encoding="utf-8"))
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
    tok_dir = args.tokenizer_dir or f"training/tokenizer/{cfg.tokenizer_id}"
    tok_hash_path = Path(tok_dir) / ".corpus_hash"
    tok_current_hash = manifest["dataset_hash"]
    # Fast Rust-backed (HF-format) tokenizers take precedence when present;
    # otherwise fall back to the cached/retrained pure-Python BPE tokenizer.
    tokenizer = None
    try:
        from .hf_tokenizer import load_hf_tokenizer as _load_hf

        tokenizer = _load_hf(tok_dir)
        tok_hash_path.write_text(tok_current_hash, encoding="utf-8")
        print(f"tokenizer reused from cache ({tok_dir})", flush=True)
    except Exception:
        tokenizer = None
    if tokenizer is None and (Path(tok_dir) / "tokenizer.json").exists() \
            and tok_hash_path.exists() \
            and tok_hash_path.read_text(encoding="utf-8").strip() == tok_current_hash:
        from .tokenizer import HerculeBPETokenizer as _Tok

        tokenizer = _Tok.load(tok_dir)
        print(f"tokenizer reused from cache ({tok_dir})", flush=True)
    if tokenizer is None:
        from .tokenizer import HerculeBPETokenizer as _Tok

        train_texts = [d.text for d in splits["train"]]
        tokenizer = _Tok.train(
            train_texts, vocab_size=cfg.vocab_size, corpus_version="hercule-seed-v1")
        tokenizer.save(tok_dir)
        tok_hash_path.write_text(tok_current_hash, encoding="utf-8")
    print(f"tokenizer vocab={tokenizer.vocab_size} merges={len(tokenizer.merges)} "
          f"checksum={tokenizer.checksum()}", flush=True)

    # ---- model on the requested device (placement is verified, not claimed) ----
    run_id = args.run_id or f"run-torch-{int(time.time())}"
    ckpt_root = Path(args.checkpoint_root) / run_id
    raw_model = TorchHerculeLM(cfg, seed=seed)
    raw_model.to(torch_device)
    for name, param in raw_model.named_parameters():
        if param.device != torch_device:
            return _fail(3, f"DEVICE_PLACEMENT_FAILED: {name} on {param.device} "
                             f"(requested {torch_device})")
    model = raw_model
    if world_size > 1:
        from .distributed import wrap_ddp

        if str(torch_device).startswith("cuda"):
            model = wrap_ddp(raw_model, device_ids=[torch_device],
                             output_device=torch_device)
        else:
            model = wrap_ddp(raw_model)  # gloo harness only, never GPU proof
        log_main(f"ddp active: backend={dist_info.get('backend')} "
                 f"world_size={world_size} rank={get_rank()}")
    core_model = getattr(model, "module", model)  # unwrap DDP for ckpt/custom ops
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, betas=(0.9, 0.999),
                                  eps=1e-8, weight_decay=0.01)
    scaler = None
    if amp == "fp16":
        scaler = torch.amp.GradScaler("cuda" if str(torch_device).startswith("cuda") else "cpu")

    start_step = 0
    resumed_state: dict = {}
    resumed_manifest: dict = {}
    if args.resume:
        try:
            resumed_manifest = ckpt.load_torch_checkpoint(
                args.resume, core_model, optimizer=optimizer, strict=True,
                map_to=str(torch_device),
                expected_tokenizer_checksum=tokenizer.checksum(),
                expected_dataset_hash=manifest["dataset_hash"])
            start_step = core_model._step_count
            resumed_state = dict(resumed_manifest.get("train_state", {}) or {})
            print(f"resumed from {args.resume} at step {start_step} "
                  f"(source={resumed_manifest.get('_load', {}).get('source_format', '?')})",
                  flush=True)
        except Exception as exc:
            return _fail(2, f"CHECKPOINT_MISMATCH/CORRUPTED: {exc}")
    print(f"model={cfg.model_id} params={core_model.parameter_count()} "
          f"seed={seed} arch={cfg.architecture_hash()} "
          f"backend=torch device={torch_device} dtype=float32 amp={amp}", flush=True)
    if str(torch_device).startswith("cuda"):
        try:
            print(f"gpu={torch.cuda.get_device_name(torch_device)} "
                  f"count={torch.cuda.device_count()} "
                  f"allocated={torch.cuda.memory_allocated(torch_device)}B", flush=True)
        except Exception:
            pass

    runtime = collect_runtime(str(torch_device), dtype="float32", amp=amp, backend="torch")
    run_manifest = {
        "run_id": run_id, "config": cfg.as_dict(), "seed": seed,
        "python": __import__("platform").python_version(),
        "numpy": np.__version__, "torch": torch.__version__,
        "cuda": getattr(torch.version, "cuda", None),
        "optimizer": "adamw", "scheduler": "cosine", "lr": args.lr,
        "batch": args.batch, "seq_len": seq_len, "steps": args.steps,
        "runtime": runtime,
        "hardware": {"cpu": __import__("platform").processor() or __import__("platform").machine(),
                     "os": f"{__import__('platform').system()} {__import__('platform').release()}",
                     "gpu": runtime["gpu_name"], "gpu_count": runtime["gpu_count"]},
    }
    micro_batch = int(args.micro_batch or args.batch)
    accum_steps = max(1, int(args.grad_accum or 1))
    num_devices = max(1, world_size)
    effective_batch = micro_batch * accum_steps * num_devices
    run_manifest.update({
        "micro_batch_size": micro_batch,
        "gradient_accumulation_steps": accum_steps,
        "effective_batch_size": effective_batch,
        "number_of_devices": num_devices,
        "device": str(torch_device), "backend": "torch", "dtype": "float32",
        "amp": amp,
        "distributed": dict(dist_info),
        "distributed_status": (f"DDP {dist_info.get('backend')} "
                               f"world_size={world_size}" if world_size > 1
                               else "NOT_IMPLEMENTED (single-device only)"),
    })

    from .data import cached_stream

    cache_dir = str(Path("training") / "streams")
    train_stream = cached_stream(tokenizer, splits["train"], seq_len,
                                 seed=seed, cache_dir=cache_dir,
                                 corpus_hash=manifest["dataset_hash"] + ":train")
    valid_stream = cached_stream(tokenizer, splits["validation"], seq_len,
                                 seed=seed, cache_dir=cache_dir,
                                 corpus_hash=manifest["dataset_hash"] + ":valid")
    if len(valid_stream) < seq_len + 1:
        print("validation split empty; monitoring train stream instead", flush=True)
        valid_stream = train_stream
    print(f"train_tokens={len(train_stream)} valid_tokens={len(valid_stream)}", flush=True)
    micro_batches = make_batches(train_stream, seq_len, micro_batch, seed=seed)
    if world_size > 1:
        # Rank-sharded round-robin over the shared deterministic order.
        micro_batches = shard_batches(micro_batches)
        log_main(f"rank {get_rank()}: {len(micro_batches)} micro-batches "
                 f"(world_size={world_size})")
    sft_marker_ids: list = []
    if str(args.sft_marker or ""):
        sft_marker_ids = tokenizer.encode(str(args.sft_marker))
        print(f"sft masking after marker ids={sft_marker_ids}", flush=True)
    try:
        valid_batches = make_batches(valid_stream, seq_len, max(1, micro_batch // 2),
                                     seed=seed + 1)
    except ValueError as exc:
        return _fail(2, str(exc))
    from .train import _write_manifests

    if is_main():
        _write_manifests(ckpt_root, run_manifest, manifest)
    if world_size > 1:
        barrier()

    # ---- loop: accumulate N micro-batches, step once ----
    from .data import mask_before_marker as _mask_fn  # noqa (re-export check)

    train_state = {"step": start_step}
    best_val = float("inf")
    deadline = time.perf_counter() + args.max_secs if args.max_secs > 0 else 0.0
    interrupted = False
    total_steps = start_step + args.steps
    tokens_seen = int(resumed_state.get("tokens_seen", 0))
    micro_index = int(resumed_state.get("micro_index", start_step * accum_steps))
    use_pin = str(torch_device).startswith("cuda")
    peak_vram = 0
    # For steady-state measurement, exclude first step (warmup)
    steady_tokens = 0
    steady_time = 0.0
    try:
        for step in range(start_step, total_steps):
            if deadline and time.perf_counter() > deadline:
                print("time budget reached; checkpointing and stopping", flush=True)
                break
            lr = cosine_lr(step, total_steps, args.lr)
            for group in optimizer.param_groups:
                group["lr"] = lr
            t0 = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            accum_loss, accum_count = 0.0, 0
            # Data pipeline timing (microseconds)
            t_data_load = 0.0
            t_h2d = 0.0
            t_forward = 0.0
            t_backward = 0.0
            t_optim = 0.0
            use_ddp_no_sync = world_size > 1 and hasattr(model, "no_sync")
            for ai in range(accum_steps):
                t_dl = time.perf_counter()
                xs_np, ys_np = micro_batches[micro_index % len(micro_batches)]
                micro_index += 1
                if sft_marker_ids:
                    ys_np = _mask_fn(ys_np, sft_marker_ids)
                t_data_load += time.perf_counter() - t_dl

                t_h = time.perf_counter()
                xs = torch.from_numpy(np.ascontiguousarray(xs_np)).to(
                    torch_device, non_blocking=use_pin)
                ys = torch.from_numpy(np.ascontiguousarray(ys_np)).to(
                    torch_device, non_blocking=use_pin)
                t_h2d += time.perf_counter() - t_h

                if xs.device != torch_device or ys.device != torch_device:
                    return _fail(3, "DEVICE_PLACEMENT_FAILED: batch not on "
                                    f"{torch_device}")
                try:
                    t_f = time.perf_counter()
                    with _amp_context(amp, str(torch_device)):
                        logits = model(xs)
                        if logits.device != torch_device:
                            return _fail(3, "DEVICE_PLACEMENT_FAILED: logits not on "
                                            f"{torch_device}")
                        loss_full = core_model.cross_entropy(logits, ys)
                    t_forward += time.perf_counter() - t_f

                    loss = loss_full / accum_steps
                except (torch.cuda.OutOfMemoryError, MemoryError):
                    return _fail(3, "OUT_OF_MEMORY: batch does not fit; reduce --batch/--seq-len")
                if not torch.isfinite(loss_full).item():
                    return _fail(3, f"TRAINING_DIVERGED: non-finite loss at step {step}")

                def _do_backward():
                    if scaler is not None:
                        scaler.scale(loss).backward()
                    else:
                        loss.backward()

                t_b = time.perf_counter()
                if use_ddp_no_sync and ai < accum_steps - 1:
                    with model.no_sync():
                        _do_backward()
                else:
                    _do_backward()
                t_backward += time.perf_counter() - t_b

                accum_loss += float(loss_full.detach().cpu().item())
                accum_count += 1
                tokens_seen += int(xs_np.size)
            mean_loss = accum_loss / max(1, accum_count)

            t_o = time.perf_counter()
            if scaler is not None:
                scaler.unscale_(optimizer)
            gnorm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0).item()
            if scaler is not None:
                scaler.step(optimizer)
                scaler.update()
            else:
                optimizer.step()
            t_optim += time.perf_counter() - t_o

            core_model._step_count = step + 1
            dt = time.perf_counter() - t0
            report_loss = float(average_object(mean_loss)) if world_size > 1 else mean_loss
            # Accumulate steady-state (exclude first step)
            if step > start_step:
                steady_tokens += eff_tokens
                steady_time += dt
            eff_tokens = micro_batch * seq_len * accum_steps
            vram_alloc = vram_res = 0
            if str(torch_device).startswith("cuda"):
                try:
                    vram_alloc = int(torch.cuda.memory_allocated(torch_device))
                    vram_res = int(torch.cuda.memory_reserved(torch_device))
                    peak_vram = max(peak_vram, int(
                        torch.cuda.max_memory_allocated(torch_device)))
                except Exception:
                    pass
            gpu_util = None
            if str(torch_device).startswith("cuda") and (step + 1) % 10 == 0:
                try:
                    gpu_util = gpu_utilization(
                        int(str(torch_device).split(":")[1])
                        if ":" in str(torch_device) else 0)
                except Exception:
                    gpu_util = None
            train_state.update({"step": step + 1, "lr": lr, "loss": float(report_loss),
                                "grad_norm": float(gnorm),
                                "micro_index": micro_index,
                                "tokens_seen": tokens_seen,
                                "gpu_util": gpu_util,
                                "vram_allocated_bytes": vram_alloc,
                                "vram_reserved_bytes": vram_res,
                                "time_data_load_s": t_data_load,
                                "time_h2d_s": t_h2d,
                                "time_forward_s": t_forward,
                                "time_backward_s": t_backward,
                                "time_optim_s": t_optim,
                                "time_total_s": dt})
            if args.metrics_log and is_main():
                import json as _json

                with open(args.metrics_log, "a", encoding="utf-8") as handle:
                    handle.write(_json.dumps({
                        "step": step + 1, "tokens": tokens_seen,
                        "loss": round(float(report_loss), 4),
                        "valid_loss": round(float(train_state.get("valid_loss", 0.0) or 0.0), 4),
                        "lr": lr, "grad_norm": round(float(gnorm), 3),
                        "tok_s": round(eff_tokens / max(dt, 1e-6), 1),
                        "micro_index": micro_index,
                        "backend": "torch", "device": str(torch_device),
                        "dtype": "float32", "amp": amp,
                        "vram_allocated_bytes": vram_alloc,
                        "vram_reserved_bytes": vram_res,
                        "gpu_util": gpu_util,
                        "time_data_load_ms": round(t_data_load * 1000, 1),
                        "time_h2d_ms": round(t_h2d * 1000, 1),
                        "time_forward_ms": round(t_forward * 1000, 1),
                        "time_backward_ms": round(t_backward * 1000, 1),
                        "time_optim_ms": round(t_optim * 1000, 1),
                        "time_total_ms": round(dt * 1000, 1),
                    }) + "\n")
            if ((step + 1) % 10 == 0 or step == start_step) and is_main():
                print(f"step={step + 1}/{total_steps} loss={report_loss:.4f} "
                      f"lr={lr:.2e} gnorm={gnorm:.2f} {dt * 1000:.0f}ms "
                      f"{eff_tokens / max(dt, 1e-6):.0f}tok/s "
                      f"(data={t_data_load*1000:.0f}ms h2d={t_h2d*1000:.0f}ms "
                      f"fwd={t_forward*1000:.0f}ms bwd={t_backward*1000:.0f}ms "
                      f"opt={t_optim*1000:.0f}ms) "
                      f"(micro={micro_batch}x{accum_steps}) [torch/{torch_device}]"
                      + (f" [rank {get_rank()}/{world_size}]" if world_size > 1 else ""),
                      flush=True)
            if (step + 1) % args.eval_every == 0:
                val_loss = _evaluate_torch(core_model, valid_batches, torch_device, amp)
                if world_size > 1:
                    val_loss = float(average_object(val_loss))
                ppl = float(np.exp(min(20.0, val_loss)))
                if is_main():
                    print(f"  valid loss={val_loss:.4f} ppl={ppl:.1f}", flush=True)
                train_state["valid_loss"] = float(val_loss)
                best_val = min(best_val, val_loss)
            if (step + 1) % args.ckpt_every == 0:
                if is_main():
                    _save_torch(ckpt_root, step + 1, core_model, optimizer, scaler,
                                tokenizer, manifest, train_state, run_manifest)
                barrier()
    except KeyboardInterrupt:
        interrupted = True
        print("TRAINING_INTERRUPTED by user; saving latest state", flush=True)
    if world_size > 1:
        barrier()
    final_step = int(train_state.get("step", start_step))
    if is_main():
        _save_torch(ckpt_root, final_step, core_model, optimizer, scaler,
                    tokenizer, manifest, train_state, run_manifest)
        ckpt.write_latest(str(Path(args.checkpoint_root)), str(ckpt_root))
    if world_size > 1:
        barrier()
    runtime_end = collect_runtime(str(torch_device), dtype="float32", amp=amp, backend="torch")
    wall = time.perf_counter() - t_start
    total_tokens = max(0, tokens_seen)
    steady_tok_s = steady_tokens / max(steady_time, 1e-6) if steady_time > 0 else 0.0
    dist_report = (f"DDP {dist_info.get('backend')} world_size={world_size} "
                   f"rank={get_rank()}" if world_size > 1
                   else "NOT_IMPLEMENTED")
    if is_main():
        print(f"done steps={train_state.get('step')} best_valid={best_val:.4f} "
              f"tokens={tokens_seen} root={ckpt_root}", flush=True)
        print(f"torch runtime: backend=torch device={torch_device} "
              f"gpu={runtime_end['gpu_name']} count={runtime_end['gpu_count']} "
              f"dtype=float32 amp={amp} "
              f"peak_vram_bytes={runtime_end['peak_allocated_memory_bytes']} "
              f"tok_s_wall={total_tokens / max(wall, 1e-6):.1f} "
              f"tok_s_steady={steady_tok_s:.1f} "
              f"distributed_status={dist_report}", flush=True)
    if world_size > 1:
        _dist_cleanup()
    return 130 if interrupted else 0


def _evaluate_torch(model: TorchHerculeLM, batches, device, amp: str) -> float:
    import torch

    was_training = model.training
    model.eval()
    losses = []
    try:
        with torch.no_grad():
            for xs_np, ys_np in batches[:8]:
                xs = torch.from_numpy(np.ascontiguousarray(xs_np)).to(device)
                ys = torch.from_numpy(np.ascontiguousarray(ys_np)).to(device)
                with _amp_context(amp, str(device)):
                    logits = model(xs)
                    loss = model.cross_entropy(logits, ys)
                losses.append(float(loss.detach().cpu().item()))
    finally:
        if was_training:
            model.train()
    return float(sum(losses) / max(1, len(losses)))


def _save_torch(ckpt_root: Path, step: int, model, optimizer, scaler,
                tokenizer, manifest, train_state, run_manifest) -> None:
    from .checkpoint import capture_torch_rng

    target = ckpt_root / f"step_{step:08d}"
    rng_state = capture_torch_rng()
    try:
        rng_state["seed"] = int(getattr(model, "seed", 0))
    except Exception:
        pass
    ckpt.save_torch_checkpoint(str(target), model, tokenizer.manifest(), manifest,
                               dict(train_state), dict(run_manifest),
                               optimizer=optimizer, scaler=scaler,
                               rng_state=rng_state)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return int(run_from_namespace(args))


if __name__ == "__main__":
    raise SystemExit(main())
