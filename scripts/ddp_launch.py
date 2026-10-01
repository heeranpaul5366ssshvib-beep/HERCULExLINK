#!/usr/bin/env python3
"""DDP launcher for HERCULE-LM torch training (Phase 2H/3G).

Spawns ``nproc`` worker processes, each running
``python -m models.hercule_lm.train`` with RANK/WORLD_SIZE/
MASTER_ADDR/MASTER_PORT set. Avoids torchrun (whose rendezvous
backend has issues on some Windows/CPU-only builds); workers use
``init_process_group(env://)`` directly via
``models.hercule_lm.distributed``.

Usage:
    python scripts/ddp_launch.py --nproc 2 --master-port 29521 -- \
        -m models.hercule_lm.train --config hercule_lm_nano \
        --backend torch --device cpu --steps 4 ...

GPU multi-GPU use:
    python scripts/ddp_launch.py --nproc 2 -- \
        -m models.hercule_lm.train --config <cfg> \
        --backend torch --device cuda --steps N ...

Exit code is 0 only if ALL ranks exit 0. Rank logs stream to
stdout prefixed with [rank N].
"""

import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pump(stream, prefix):
    for line in iter(stream.readline, ""):
        if not line:
            break
        sys.stdout.write(f"[rank {prefix}] {line}")
    sys.stdout.flush()


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="hercule-ddp-launch")
    parser.add_argument("--nproc", type=int, default=2)
    parser.add_argument("--master-addr", default="127.0.0.1")
    parser.add_argument("--master-port", default="29521")
    parser.add_argument("train_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    rest = list(args.train_args)
    if rest and rest[0] == "--":
        rest = rest[1:]
    if not rest:
        print("usage: ddp_launch.py --nproc N -- [python-args...]", file=sys.stderr)
        return 2

    procs = []
    for rank in range(args.nproc):
        env = dict(os.environ)
        env["RANK"] = str(rank)
        env["LOCAL_RANK"] = str(rank)
        env["WORLD_SIZE"] = str(args.nproc)
        env["MASTER_ADDR"] = args.master_addr
        env["MASTER_PORT"] = str(args.master_port)
        cmd = [sys.executable] + rest
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)
        procs.append((rank, proc))
        threading.Thread(target=_pump, args=(proc.stdout, rank), daemon=True).start()

    codes = []
    for rank, proc in procs:
        codes.append(proc.wait())
    print(f"ddp_launch: nproc={args.nproc} exit_codes={codes}", flush=True)
    return 0 if all(c == 0 for c in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
