from __future__ import annotations
"""N4 canonical benchmark (N4 §5/§19): timed training components.

Usage::

    python -m training.benchmark --config hercule_lm_micro --steps 60

Measures data/tokenizer/batch/forward/backward/clip/optimizer/eval/
checkpoint stages separately plus peak process memory (Win32 API,
stdlib only). Writes JSON to ``training/benchmarks/``. Versioned
config echoed into the record (N4_BENCHMARK_CONFIG v1).
"""

import argparse
import json
import sys
import time
from pathlib import Path

BENCHMARK_VERSION = "N4_BENCHMARK_CONFIG v1"


def _process_memory() -> tuple:
    """(peak_ws_mb, ws_mb) via Win32 API, stdlib only (0.0s on failure)."""
    try:
        import ctypes
        from ctypes import wintypes

        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class MemInfo(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("pagefault", wintypes.DWORD),
                        ("peakws", ctypes.c_size_t), ("ws", ctypes.c_size_t),
                        ("quotapeakpaged", ctypes.c_size_t), ("quotapaged", ctypes.c_size_t),
                        ("quotapeaknonpaged", ctypes.c_size_t), ("quotanonpaged", ctypes.c_size_t),
                        ("pagefile", ctypes.c_size_t), ("peakpagefile", ctypes.c_size_t)]

        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                               ctypes.POINTER(MemInfo), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        info = MemInfo()
        info.cb = ctypes.sizeof(info)
        ok = psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(),
                                        ctypes.byref(info), info.cb)
        if not ok:
            return 0.0, 0.0
        return round(info.peakws / 1e6, 1), round(info.ws / 1e6, 1)
    except Exception:
        return 0.0, 0.0


def peak_rss_mb() -> float:
    return _process_memory()[0]


def rss_mb() -> float:
    return _process_memory()[1]


def main(argv=None) -> int:
    from models.hercule_lm.threads import configure_threads as _ct

    _ct()  # must precede numpy import to affect BLAS threading
    import numpy as np

    parser = argparse.ArgumentParser(prog="hercule-lm-benchmark")
    parser.add_argument("--config", default="hercule_lm_micro")
    parser.add_argument("--corpus-dir", default="training/data/raw")
    parser.add_argument("--sources", default="training/data/sources.json")
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--seq-len", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="training/benchmarks")
    args = parser.parse_args(argv)

    from models.hercule_lm import checkpoint as ckpt
    from models.hercule_lm.config import load_config
    from models.hercule_lm.data import (dataset_manifest, encode_split,
                                        load_documents, make_batches,
                                        split_documents, validate_documents,
                                        DataSource)
    from models.hercule_lm.model import HerculeLM
    from models.hercule_lm.tokenizer import HerculeBPETokenizer

    stage: dict = {}
    mark = time.perf_counter()
    config = load_config(args.config)
    seq_len = int(args.seq_len or config.context_length // 2)
    sources = [DataSource(**s) for s in
               json.loads(Path(args.sources).read_text(encoding="utf-8"))]
    docs = load_documents(args.corpus_dir, sources, paragraphs=True)
    validate_documents(docs, ["HERCULE-authored (MIT, repo)"])
    splits = split_documents(docs)
    stage["data_load_s"] = round(time.perf_counter() - mark, 3)

    mark = time.perf_counter()
    tokenizer = HerculeBPETokenizer.train(
        [d.text for d in splits["train"]], vocab_size=config.vocab_size,
        corpus_version="bench")
    stage["tokenizer_train_s"] = round(time.perf_counter() - mark, 3)

    mark = time.perf_counter()
    stream = encode_split(tokenizer, splits["train"], seq_len, seed=args.seed)
    batches = make_batches(stream, seq_len, args.batch, seed=args.seed)
    stage["encode_batch_s"] = round(time.perf_counter() - mark, 3)

    mark = time.perf_counter()
    model = HerculeLM(config, seed=args.seed)
    stage["init_s"] = round(time.perf_counter() - mark, 3)

    comp = {"forward": [], "backward": [], "clip_opt": [], "step": []}
    first_loss, last_loss = None, None
    for step in range(args.steps):
        xs, ys = batches[step % len(batches)]
        t0 = time.perf_counter()
        logits, cache = model.forward(xs)
        loss, grads = model.loss_and_backward(logits, cache, ys)
        t1 = time.perf_counter()
        model.clip_grads(grads, 1.0)
        model.adamw_step(grads, 3e-4)
        t2 = time.perf_counter()
        comp["step"].append(t2 - t0)
        if first_loss is None:
            first_loss = float(loss)
        last_loss = float(loss)
    # Split forward vs backward honestly on a fresh timed pair.
    xs, ys = batches[0]
    repeats = 5
    t0 = time.perf_counter()
    for _ in range(repeats):
        logits, cache = model.forward(xs)
    fwd = (time.perf_counter() - t0) / repeats
    t0 = time.perf_counter()
    for _ in range(repeats):
        logits, cache = model.forward(xs)
        _, grads = model.loss_and_backward(logits, cache, ys)
    bwd = (time.perf_counter() - t0) / repeats - fwd
    t0 = time.perf_counter()
    for _ in range(20):
        model.clip_grads(grads, 1.0)
        model.adamw_step(grads, 3e-4)
    clip_opt = (time.perf_counter() - t0) / 20

    # Checkpoint save/load cost (one cycle, tmp dir; integrity verified).
    import tempfile as _tf

    from models.hercule_lm import checkpoint as _ckpt

    with _tf.TemporaryDirectory(prefix="hercule-bench-ckpt-") as _cd:
        t0 = time.perf_counter()
        saved = _ckpt.save_checkpoint(
            str(Path(_cd) / "ckpt"), model, tokenizer.manifest(),
            {"name": "bench", "version": "v1"}, {"step": 0}, {"run_id": "bench"})
        ckpt_save_s = time.perf_counter() - t0
        ckpt_bytes = sum(p.stat().st_size for p in Path(saved).rglob("*") if p.is_file())
        from models.hercule_lm.model import HerculeLM as _LM

        fresh = _LM(config, seed=999)
        t0 = time.perf_counter()
        _ckpt.load_checkpoint(saved, fresh, strict=True)
        ckpt_load_s = time.perf_counter() - t0
        ckpt_roundtrip_ok = all(
            bool((model.params[k] == fresh.params[k]).all()) for k in model.params)

    step_times = comp["step"]
    record = {
        "benchmark": BENCHMARK_VERSION,
        "config": config.as_dict(), "params": model.parameter_count(),
        "steps": args.steps, "batch": args.batch, "seq_len": seq_len,
        "seed": args.seed,
        "stages_s": stage,
        "forward_s": round(fwd, 4), "backward_s": round(max(0.0, bwd), 4),
        "clip_opt_s": round(clip_opt, 5),
        "step_mean_s": round(sum(step_times) / len(step_times), 4),
        "step_p95_s": round(sorted(step_times)[int(0.95 * (len(step_times) - 1))], 4),
        "tokens_per_sec": round(args.batch * seq_len / (sum(step_times) / len(step_times)), 1),
        "loss_first": first_loss, "loss_last": last_loss,
        "ckpt_save_s": round(ckpt_save_s, 3), "ckpt_load_s": round(ckpt_load_s, 3),
        "ckpt_bytes": int(ckpt_bytes), "ckpt_roundtrip_ok": bool(ckpt_roundtrip_ok),
        "peak_rss_mb": peak_rss_mb(), "rss_mb": rss_mb(),
        "python": platform.python_version() if (platform := __import__("platform")) else "?",
        "numpy": np.__version__, "torch": None, "cuda": False,
        "cpu": platform.processor() or platform.machine(),
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"bench_{config.model_id}_{args.batch}x{seq_len}_{args.steps}.json"
    (out_dir / name).write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
