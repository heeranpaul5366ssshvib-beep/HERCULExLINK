from __future__ import annotations
"""Local controller CLI + train_remote() (spec §11/§14).

Orchestration only: prepare -> upload -> train -> download ->
evaluate -> decide. Large training NEVER runs on local CPU when a
remote GPU run is available (enforced: --new-run refuses CPU fallback
for training workloads).
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from tools.kaggle_trainer import artifacts as _art
from tools.kaggle_trainer import kaggle_executor as _kx
from tools.kaggle_trainer import monitor as _mon
from tools.kaggle_trainer.bundler import build_bundle
from tools.kaggle_trainer.checkpoints import adopt, approved, register
from tools.kaggle_trainer.discover import (active_config, backend_capability,
                                           find_root, inventory)
from tools.kaggle_trainer.evaluate import deltas, run_eval, verify_checkpoint

RUNS_DB = "artifacts/kaggle_runs/RUNS.json"


def _runs() -> Dict[str, Any]:
    try:
        return json.loads(Path(RUNS_DB).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_runs(rows: Dict[str, Any]) -> None:
    Path(RUNS_DB).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(RUNS_DB + ".tmp")
    tmp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    tmp.replace(RUNS_DB)


def _slug(user: str, run_id: str) -> str:
    return f"{user}/hercule-lm-{run_id}"


def cmd_new_run(args) -> int:
    creds = _kx.creds_ok()
    if not creds["ok"]:
        print(f"BLOCKED: {creds['reason']}")
        print("Setup: pip install kaggle; set KAGGLE_USERNAME + KAGGLE_KEY "
              "(https://www.kaggle.com/settings/account -> API -> Create New Token).")
        return 2
    root = find_root()
    inv = inventory(str(root))
    if inv["parts"].get("models/hercule_lm") != "present":
        print("BLOCKED: models/hercule_lm missing")
        return 2
    try:
        cfg = active_config(str(root), args.config)
    except Exception as exc:
        print(f"BLOCKED: bad config ({exc})")
        return 2
    run_id = args.run_id or f"run-{int(time.time())}"
    user = creds.get("username") or __import__("os").environ.get("KAGGLE_USERNAME", "")
    if not user:
        print("BLOCKED: authenticated Kaggle CLI has no account username")
        return 2
    params = {"config": args.config, "steps": args.steps, "batch": args.batch,
              "seed": args.seed, "mode": args.mode, "run_id": run_id,
              "corpus_dir": "training/data/raw",
              "sources": "training/data/sources.json",
              "model": cfg["model_id"], "arch_hash": cfg["arch_hash"]}
    print(f"bundle: config={cfg['model_id']} params={cfg['params']}")
    bundle = build_bundle(
        str(root), str(Path(f"artifacts/kaggle_runs/{run_id}/bundle")),
        params=params,
        extra_files=["tools/kaggle_trainer/remote_job.py"])
    print(f"bundle: {bundle['files']} files hash={bundle['bundle_hash'][:16]}")
    ds_slug = f"hercule-bundle-{run_id}"
    ds_dir = str(Path(f"artifacts/kaggle_runs/{run_id}/dataset"))
    _kx.make_dataset_dir(bundle["bundle_dir"], ds_dir, user, ds_slug,
                         f"HERCULE bundle {run_id}")
    print("uploading dataset...")
    res = _kx.datasets_create(ds_dir)
    if res["returncode"] != 0:
        print(f"BLOCKED dataset upload failed:\n{res['tail']}")
        return 2
    kdir = str(Path(f"artifacts/kaggle_runs/{run_id}/kernel"))
    _kx.make_kernel_dir(kdir, user, f"hercule-lm-{run_id}",
                        f"HERCULE-LM {run_id}", ds_slug, params,
                        gpu=not args.cpu)
    print("pushing kernel (GPU=%s)..." % (not args.cpu))
    res = _kx.kernels_push(kdir)
    print(res["tail"][-1500:])
    if res["returncode"] != 0:
        print("BLOCKED kernel push failed")
        return 2
    rows = _runs()
    rows[run_id] = {"kernel": _slug(user, run_id),
                    "dataset": f"{user}/{ds_slug}", "params": params,
                    "status": "submitted", "created": time.time()}
    _save_runs(rows)
    print(f"submitted run_id={run_id} kernel={rows[run_id]['kernel']}")
    return 0


def cmd_status(args) -> int:
    rows = _runs()
    rec = rows.get(args.run_id or latest_id())
    if not rec:
        print("no such run (see --latest)")
        return 2
    res = _kx.kernels_status(rec["kernel"])
    print(res["output"][-2000:])
    return 0


def cmd_logs(args) -> int:
    rows = _runs()
    rec = rows.get(args.run_id or latest_id())
    if not rec:
        print("no such run")
        return 2
    dest = str(Path(f"artifacts/kaggle_runs/{args.run_id or latest_id()}/logs"))
    Path(dest).mkdir(parents=True, exist_ok=True)
    res = _kx.kernels_output(rec["kernel"], dest)
    log = Path(dest) / "run.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        print("\n".join(lines[-int(args.lines or 40):]))
        prog = _mon.parse_progress("\n".join(lines))
        print(f"progress: {prog}")
    else:
        print(res["tail"][-1500:])
    return 0


def cmd_download(args) -> int:
    rows = _runs()
    run_id = args.run_id or latest_id()
    rec = rows.get(run_id)
    if not rec:
        print("no such run")
        return 2
    dest = _art.run_dir("", run_id)
    res = _art.download(rec["kernel"], str(dest))
    print(f"downloaded {len(res['files'])} files -> {dest}")
    ver = _art.verify_run(str(dest))
    print(json.dumps(ver["checks"], indent=1))
    ckpts = sorted((dest / "checkpoints").rglob("step_*")) if (dest / "checkpoints").exists() else []
    record = {"run_id": run_id, "status": ver["status"].get("status", "?"),
              "gpu": (ver["status"].get("gpu") or {}).get("devices", "?"),
              "steps_completed": (ver["status"].get("smoke") or {}) and None,
              "checkpoint_path": str(ckpts[-1]) if ckpts else "",
              "artifact_path": str(dest),
              "failure_reason": ver["status"].get("code", "") if ver["status"].get("status") == "failed" else ""}
    _art.write_final_report(str(dest), record)
    return 0 if ver["ok"] else 2


def cmd_evaluate(args) -> int:
    rows = _runs()
    run_id = args.run_id or latest_id()
    dest = Path(f"artifacts/kaggle_runs/{run_id}")
    ckpts = sorted(dest.rglob("step_*"))
    if not ckpts:
        print("BLOCKED: no checkpoint downloaded (run --download first)")
        return 2
    tok_dir = args.tokenizer_dir or ""
    ver = verify_checkpoint(str(ckpts[-1]), tok_dir)
    print(json.dumps(ver, indent=1))
    scores = run_eval(str(ckpts[-1]), tok_dir) if tok_dir else {}
    print("scores:", scores)
    prev = approved()
    if prev and prev.get("eval"):
        print("deltas:", deltas(scores, prev["eval"]))
    register(run_id, str(ckpts[-1]), scores)
    print("registered (NOT approved: adoption requires explicit --adopt)")
    return 0


def latest_id() -> str:
    rows = _runs()
    if not rows:
        return ""
    return max(rows.items(), key=lambda kv: kv[1].get("created", 0))[0]


def train_remote(model: str = "hercule-lm-micro", dataset: str = "seed",
                 config: str = "", steps: int = 100, gpu: bool = True,
                 resume_from: Optional[str] = None) -> Dict[str, Any]:
    """High-level remote training (spec §14). Returns structured result."""
    rec: Dict[str, Any] = {"run_id": "", "status": "blocked", "gpu": None,
                           "steps_completed": 0, "tokens_seen": 0,
                           "train_loss": None, "validation_loss": None,
                           "tokens_per_second": None, "checkpoint_path": "",
                           "artifact_path": "", "evaluation_result": {},
                           "failure_reason": ""}
    creds = _kx.creds_ok()
    if not creds["ok"]:
        rec["failure_reason"] = creds["reason"]
        return rec
    ns = argparse.Namespace(config=config or model.replace("-", "_"),
                            steps=steps, batch=8, seed=0, mode="benchmark",
                            run_id=f"api-{int(time.time())}", cpu=not gpu)
    code = cmd_new_run(ns)
    if code != 0:
        rec["failure_reason"] = "submission failed"
        return rec
    rec["run_id"] = ns.run_id
    rec["status"] = "submitted"
    return rec


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hercule-kaggle")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new-run")
    p.add_argument("--config", default="hercule_lm_micro")
    p.add_argument("--steps", type=int, default=100)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--mode", default="benchmark",
                   choices=["smoke", "benchmark", "train"])
    p.add_argument("--run-id", default="")
    p.add_argument("--cpu", action="store_true",
                   help="CPU kernel (debug only; never for real training)")
    for name in ("status", "logs", "download", "evaluate", "cancel"):
        q = sub.add_parser(name)
        q.add_argument("--run-id", default="")
        if name == "logs":
            q.add_argument("--lines", type=int, default=40)
        if name == "evaluate":
            q.add_argument("--tokenizer-dir", default="")
    sub.add_parser("latest").add_argument("--x", nargs="?", default="")
    args = parser.parse_args(argv)
    if args.cmd == "new-run":
        return cmd_new_run(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "logs":
        return cmd_logs(args)
    if args.cmd == "download":
        return cmd_download(args)
    if args.cmd == "evaluate":
        return cmd_evaluate(args)
    if args.cmd == "latest":
        print(latest_id() or "no runs")
        return 0
    if args.cmd == "cancel":
        print("cancel: use `kaggle kernels status` / Kaggle UI to cancel; "
              "local record kept for audit")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
