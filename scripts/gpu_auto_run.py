#!/usr/bin/env python3
"""Phase 5 GPU auto-runner: full GPU validation sequence in one command.

Designed to execute automatically on the first GPU-capable environment
it is placed on (incl. T4-class). On GPU-less boxes it exits 3 with
GPU work honestly NOT_RUN after completing GPU-independent checks.

Sequence (all bounded; NEVER full pretraining):
  1. hardware inventory + BF16/FP16 support probe
  2. CUDA smoke (nano, 4 steps): placement/grads/vram/checkpoint proof
  3. FP32 benchmarks: micro, s10m, 100m (bounded --steps, steady-state)
  4. CUDA checkpoint -> terminate -> reload -> resume verification
  5. AMP: bf16 (+ fp16 where supported), finite-loss + throughput
  6. 2-GPU DDP when >= 2 devices (else NOT_RUN)
  7. writes reports/frontier_program/phase5_*.json

Usage:
  python scripts/gpu_auto_run.py [--steps 10] [--run-root <dir>]
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports" / "frontier_program"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                          text=True, timeout=3600, **kw)


def detect() -> dict:
    import torch

    cuda = bool(torch.cuda.is_available())
    info: dict = {
        "torch": torch.__version__,
        "cuda_available": cuda,
        "cuda_version": getattr(torch.version, "cuda", None) if cuda else None,
        "cudnn": torch.backends.cudnn.version() if cuda else None,
        "gpu_count": int(torch.cuda.device_count()) if cuda else 0,
        "devices": [],
        "bf16": False, "fp16": False,
    }
    if cuda:
        for i in range(info["gpu_count"]):
            p = torch.cuda.get_device_properties(i)
            info["devices"].append({
                "index": i, "name": p.name,
                "vram_gb": round(p.total_memory / 1e9, 1),
                "compute_capability": f"{p.major}.{p.minor}",
                "bf16": p.major >= 8, "fp16": True,
            })
        info["bf16"] = any(d["bf16"] for d in info["devices"])
        info["fp16"] = True
    return info


def train(args, run_id, ckpt_root) -> dict:
    """Run one bounded training; return parsed evidence (never invented)."""
    cmd = ([sys.executable, "-m", "models.hercule_lm.train"] + args
           + ["--run-id", run_id, "--checkpoint-root", str(ckpt_root)])
    t0 = time.perf_counter()
    proc = _run(cmd)
    wall = time.perf_counter() - t0
    out = proc.stdout + proc.stderr
    rec = {"returncode": proc.returncode, "wall_s": round(wall, 1),
           "backend_torch": "backend=torch" in out,
           "device_cuda": "/cuda" in out or "device=cuda" in out,
           "peak_vram": None, "steady_toks": None, "loss_first": None,
           "loss_last": None, "ckpt": None}
    for line in out.splitlines():
        if "peak_vram_bytes=" in line:
            try:
                rec["peak_vram"] = int(line.split("peak_vram_bytes=")[1].split()[0])
            except (ValueError, IndexError):
                pass
        if "tok_s_steady=" in line:
            try:
                rec["steady_toks"] = float(line.split("tok_s_steady=")[1].split()[0])
            except (ValueError, IndexError):
                pass
        if line.startswith("step="):
            try:
                loss = float(line.split("loss=")[1].split()[0])
                if rec["loss_first"] is None:
                    rec["loss_first"] = loss
                rec["loss_last"] = loss
            except (ValueError, IndexError):
                pass
    ckpts = sorted((ckpt_root / run_id).glob("step_*")) if (ckpt_root / run_id).exists() else []
    rec["ckpt"] = str(ckpts[-1]) if ckpts else None
    return rec


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="hercule-gpu-auto-run")
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--run-root", default="training/checkpoints")
    args = parser.parse_args(argv)

    REPORTS.mkdir(parents=True, exist_ok=True)
    hw = detect()
    (REPORTS / "phase5_hardware.json").write_text(
        json.dumps({"timestamp": _utcnow(), **hw}, indent=1), encoding="utf-8")
    print(json.dumps(hw, indent=1))
    if not hw["cuda_available"]:
        stub = {"timestamp": _utcnow(), "status": "BLOCKED",
                "reason": "0 CUDA devices; GPU work NOT_RUN",
                "cuda": "BLOCKED", "fp32": "NOT_RUN", "amp": "NOT_RUN",
                "ddp": "NOT_RUN", "fsdp": "NOT_RUN", "100m": "NOT_RUN"}
        for name in ("phase5_cuda_smoke", "phase5_fp32", "phase5_cuda_resume",
                     "phase5_amp", "phase5_ddp", "phase5_final",
                     "phase6_gpu_hook"):
            (REPORTS / f"{name}.json").write_text(
                json.dumps(stub, indent=1), encoding="utf-8")
        print("No CUDA GPU: GPU work NOT_RUN (stubs written).")
        return 3

    ckpt_root = Path(args.run_root)
    res: dict = {"timestamp": _utcnow(), "hardware": hw, "steps": args.steps}

    # 2. smoke
    smoke = train(["--config", "hercule_lm_nano", "--backend", "torch",
                   "--device", "cuda", "--steps", "4", "--batch", "4",
                   "--corpus-dir", "training/data/overfit",
                   "--sources", "training/data/overfit/sources.json"],
                  "p5-smoke", ckpt_root)
    verified = (smoke["returncode"] == 0 and smoke["device_cuda"]
                and (smoke["peak_vram"] or 0) > 0 and smoke["ckpt"]
                and smoke["loss_first"] is not None)
    res["smoke"] = {**smoke, "cuda_verified": bool(verified)}
    (REPORTS / "phase5_cuda_smoke.json").write_text(
        json.dumps(res["smoke"], indent=1), encoding="utf-8")
    if not verified:
        res["status"] = "CUDA_BLOCKED (smoke failed)"
        (REPORTS / "phase5_final.json").write_text(json.dumps(res, indent=1))
        return 2

    # 3. FP32 benchmarks
    fp32 = {}
    for cfg in ("hercule_lm_micro", "hercule_lm_s10m", "hercule_lm_100m"):
        fp32[cfg] = train(["--config", cfg, "--backend", "torch",
                           "--device", "cuda", "--steps", args.steps,
                           "--batch", "8"], f"p5-fp32-{cfg}", ckpt_root)
    res["fp32"] = fp32
    (REPORTS / "phase5_fp32.json").write_text(json.dumps(fp32, indent=1))

    # 4. ckpt -> terminate -> resume (fresh process, --resume)
    r0 = train(["--config", "hercule_lm_nano", "--backend", "torch",
                "--device", "cuda", "--steps", "4", "--batch", "4",
                "--corpus-dir", "training/data/overfit",
                "--sources", "training/data/overfit/sources.json",
                "--ckpt-every", "2"], "p5-resume-a", ckpt_root)
    mid = sorted((ckpt_root / "p5-resume-a").glob("step_*"))[-1]
    r1 = train(["--config", "hercule_lm_nano", "--backend", "torch",
                "--device", "cuda", "--steps", "2", "--batch", "4",
                "--corpus-dir", "training/data/overfit",
                "--sources", "training/data/overfit/sources.json",
                "--resume", str(mid)], "p5-resume-b", ckpt_root)
    res["resume"] = {"base": r0, "resumed": r1,
                     "ok": r1["returncode"] == 0 and r1["ckpt"] is not None}
    (REPORTS / "phase5_cuda_resume.json").write_text(
        json.dumps(res["resume"], indent=1))

    # 5. AMP
    amp = {}
    if hw["bf16"]:
        amp["bf16"] = train(["--config", "hercule_lm_micro", "--backend",
                             "torch", "--device", "cuda", "--amp", "bf16",
                             "--steps", args.steps, "--batch", "8"],
                            "p5-amp-bf16", ckpt_root)
    else:
        amp["bf16"] = {"status": "NOT_RUN (no BF16-capable GPU)"}
    amp["fp16"] = train(["--config", "hercule_lm_micro", "--backend",
                         "torch", "--device", "cuda", "--amp", "fp16",
                         "--steps", args.steps, "--batch", "8"],
                        "p5-amp-fp16", ckpt_root)
    res["amp"] = amp
    (REPORTS / "phase5_amp.json").write_text(json.dumps(amp, indent=1))

    # 6. DDP when >= 2 GPUs
    if hw["gpu_count"] >= 2:
        ddp = _run([sys.executable, "scripts/ddp_launch.py", "--nproc", "2",
                    "--", "-m", "models.hercule_lm.train",
                    "--config", "hercule_lm_nano", "--backend", "torch",
                    "--device", "cuda", "--steps", "4", "--batch", "4",
                    "--corpus-dir", "training/data/overfit",
                    "--sources", "training/data/overfit/sources.json",
                    "--run-id", "p5-ddp",
                    "--checkpoint-root", str(ckpt_root / "p5-ddp-tmp")])
        res["ddp"] = {"returncode": ddp.returncode,
                      "tail": (ddp.stdout + ddp.stderr)[-1500:]}
    else:
        res["ddp"] = {"status": "NOT_RUN (needs >= 2 GPUs)"}
    (REPORTS / "phase5_ddp.json").write_text(json.dumps(res["ddp"], indent=1))

    # 7. Phase 6Q hook: post-training micro smokes (bounded, guarded).
    res["posttrain_hook"] = posttrain_hook(ckpt_root)
    (REPORTS / "phase6_gpu_hook.json").write_text(
        json.dumps(res["posttrain_hook"], indent=1), encoding="utf-8")

    res["status"] = "GPU_EXECUTED"
    (REPORTS / "phase5_final.json").write_text(json.dumps(res, indent=1))
    print(f"GPU auto-run complete: status={res['status']}")
    return 0


def posttrain_hook(ckpt_root) -> dict:
    """Bounded post-training smokes on CUDA (Phase 6Q).

    SFT nano 2-step smoke + eval-harness reference run. Any failure is
    recorded, never fatal to the main GPU sequence.
    """
    hook: dict = {"timestamp": _utcnow(), "sft_smoke": None,
                  "eval_reference": None}
    try:
        hook["sft_smoke"] = train(
            ["--config", "hercule_lm_nano", "--backend", "torch",
             "--device", "cuda", "--steps", "2", "--batch", "2",
             "--corpus-dir", "training/data/overfit",
             "--sources", "training/data/overfit/sources.json",
             "--sft-marker", "<|response|>"],
            "p6-sft-smoke", ckpt_root)
    except Exception as exc:
        hook["sft_smoke"] = {"status": f"ERROR: {exc}"}
    try:
        sys.path.insert(0, str(ROOT))
        from models.hercule_lm.eval_harness import (SUITES, reference_predict,
                                                    run_all)

        rep = run_all(reference_predict, model_id="reference-ceiling",
                      suites=["MATH", "STRUCTURED_OUTPUT", "SAFETY"])
        hook["eval_reference"] = {
            s: rep["suites"][s]["mean"] for s in ("MATH", "STRUCTURED_OUTPUT", "SAFETY")}
    except Exception as exc:
        hook["eval_reference"] = {"status": f"ERROR: {exc}"}
    return hook


if __name__ == "__main__":
    raise SystemExit(main())
