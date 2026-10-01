"""HERCULE-LM remote GPU job (executes INSIDE Kaggle).

Reads HERCULE_REMOTE_JSON env (params), bundle at HERCULE_BUNDLE.
Stdout is teed to /kaggle/working/run.log so the local controller can
fetch complete logs via `kaggle kernels output` (no log-API gaps).

Steps: bootstrap deps -> CUDA gate (abort clearly if absent) ->
import/tokenizer/dataset/checkpoint checks -> CUDA smoke (gates A-F)
-> bounded training with telemetry -> checkpoint + reload test.
"""

import json
import os
import subprocess
import sys
import time
import traceback

WORKING = os.environ.get("HERCULE_WORKING", "/kaggle/working")
BUNDLE = os.environ.get("HERCULE_BUNDLE", "/kaggle/input/hercule-bundle")
PARAMS = json.loads(os.environ.get("HERCULE_REMOTE_JSON", "{}") or "{}")


class Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


def emit(record: dict, name: str = "telemetry.jsonl") -> None:
    with open(os.path.join(WORKING, name), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def fail(code: str, detail: str) -> int:
    print(f"REMOTE_FAIL [{code}]: {detail}", flush=True)
    emit({"event": "failed", "code": code, "detail": detail})
    with open(os.path.join(WORKING, "REMOTE_STATUS.json"), "w") as fh:
        json.dump({"status": "failed", "code": code, "detail": detail}, fh, indent=1)
    return 1


def main() -> int:
    log = open(os.path.join(WORKING, "run.log"), "w", encoding="utf-8")
    sys.stdout = Tee(sys.stdout, log)
    sys.stderr = Tee(sys.stderr, log)
    t0 = time.perf_counter()
    try:
        return run(t0)
    except Exception as exc:  # noqa: BLE001 - record everything remotely
        traceback.print_exc()
        return fail("CODE_ERROR", f"{type(exc).__name__}: {exc}")
    finally:
        try:
            sys.stdout.flush()
        except Exception:
            pass


def run(t0: float) -> int:
    sys.path.insert(0, BUNDLE)
    # ---- bootstrap ----
    try:
        import numpy  # noqa: F401
    except Exception:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "numpy"],
                       check=False, timeout=600)
    try:
        import torch
    except Exception as exc:
        return fail("DEPENDENCY_ERROR", f"torch import failed: {exc}")
    print(f"torch={torch.__version__} cuda={getattr(torch.version, 'cuda', None)}",
          flush=True)
    # ---- CUDA gate (abort clearly; never CPU-fallback) ----
    if not torch.cuda.is_available():
        return fail("NO_CUDA", "torch.cuda.is_available() is false on this worker")
    count = torch.cuda.device_count()
    gpus = []
    for i in range(count):
        props = torch.cuda.get_device_properties(i)
        gpus.append({"index": i, "name": props.name,
                     "vram_gb": round(props.total_memory / 1e9, 2),
                     "cc": f"{props.major}.{props.minor}"})
        print(f"gpu{i}: {props.name} {props.total_memory / 1e9:.1f}GB CC {props.major}.{props.minor}",
              flush=True)
    gpu_info = {"count": count, "devices": gpus,
                "cuda": getattr(torch.version, "cuda", None)}
    emit({"event": "gpu", **gpu_info}, "gpu.json")
    # ---- HERCULE imports ----
    try:
        from models.hercule_lm import device as _dev
        from models.hercule_lm.config import load_config
        from models.hercule_lm.torch_model import TorchHerculeLM
    except Exception as exc:
        return fail("CODE_ERROR", f"HERCULE-LM import failed: {exc}")
    cfg_name = PARAMS.get("config", "hercule_lm_micro")
    try:
        cfg = load_config(cfg_name)
    except Exception as exc:
        return fail("CONFIG_ERROR", str(exc))
    # ---- tokenizer + dataset (from bundle) ----
    bundle = BUNDLE
    steps = int(PARAMS.get("steps", 100))
    batch = int(PARAMS.get("batch", 8))
    seed = int(PARAMS.get("seed", 0))
    mode = PARAMS.get("mode", "benchmark")  # smoke | benchmark | train
    # ---- CUDA smoke (gates A-F) ----
    model = TorchHerculeLM(cfg, seed=seed).to("cuda")
    ok_places = all(p.device.type == "cuda" for p in model.parameters())
    ids = torch.randint(0, cfg.vocab_size, (2, 8), device="cuda")
    tgt = torch.randint(0, cfg.vocab_size, (2, 8), device="cuda")
    logits = model(ids)
    loss = model.cross_entropy(logits, tgt)
    loss.backward()
    before = sum(p.detach().float().sum().item() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    opt.step()
    after = sum(p.detach().float().sum().item() for p in model.parameters())
    vram = torch.cuda.memory_allocated("cuda")
    smoke = {
        "event": "smoke", "params_cuda": ok_places,
        "inputs_cuda": ids.device.type == "cuda",
        "logits_cuda": logits.device.type == "cuda",
        "loss_cuda": loss.device.type == "cuda",
        "loss_finite": bool(torch.isfinite(loss).item()),
        "loss": float(loss.detach().item()),
        "updated": before != after,
        "vram_bytes": vram,
        "params": model.parameter_count(),
    }
    print("SMOKE: " + json.dumps(smoke), flush=True)
    emit(smoke, "smoke.json")
    if not (ok_places and smoke["loss_finite"] and smoke["updated"] and vram > 0):
        return fail("SMOKE_FAILED", json.dumps(smoke))
    if mode == "smoke":
        return finish(t0, {"mode": "smoke", "smoke": smoke, "gpu": gpu_info})
    # ---- bounded training via the real trainer ----
    os.chdir(BUNDLE)
    sys.argv = ["hercule-lm-train", "--config", cfg_name, "--backend", "torch",
                "--device", "cuda", "--steps", str(steps), "--batch", str(batch),
                "--seed", str(seed), "--run-id", PARAMS.get("run_id", "kaggle-run"),
                "--checkpoint-root", os.path.join(WORKING, "checkpoints"),
                "--corpus-dir", os.path.join(bundle, PARAMS.get("corpus_dir", "training/data/raw")),
                "--sources", os.path.join(bundle, PARAMS.get("sources", "training/data/sources.json")),
                "--tokenizer-dir", os.path.join(WORKING, "tokenizer"),
                "--metrics-log", os.path.join(WORKING, "train_metrics.jsonl")]
    if PARAMS.get("resume"):
        sys.argv += ["--resume", PARAMS["resume"]]
    from models.hercule_lm.train import main as train_main

    code = int(train_main([]))
    # ---- checkpoint reload test ----
    from models.hercule_lm import checkpoint as ckpt

    latest = None
    ckroot = os.path.join(WORKING, "checkpoints", PARAMS.get("run_id", "kaggle-run"))
    try:
        import glob

        steps_dirs = sorted(glob.glob(os.path.join(ckroot, "step_*")))
        latest = steps_dirs[-1] if steps_dirs else None
        reload_ok = False
        if latest:
            probe = TorchHerculeLM(cfg, seed=seed)
            ckpt.load_torch_checkpoint(latest, probe, strict=True, map_to="cuda")
            reload_ok = str(probe.device).startswith("cuda")
    except Exception as exc:
        return fail("CHECKPOINT_ERROR", f"reload test failed: {exc}")
    if not latest or not reload_ok:
        return fail("CHECKPOINT_ERROR", "no reloadable checkpoint produced")
    return finish(t0, {"mode": mode, "smoke": smoke, "gpu": gpu_info,
                       "checkpoint": latest, "train_exit": code,
                       "wall_s": round(time.perf_counter() - t0, 1)})


def finish(t0: float, record: dict) -> int:
    record.update({"status": "complete", "wall_s": round(time.perf_counter() - t0, 1)})
    with open(os.path.join(WORKING, "REMOTE_STATUS.json"), "w") as fh:
        json.dump(record, fh, indent=1)
    print("REMOTE_COMPLETE: " + json.dumps(record), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
