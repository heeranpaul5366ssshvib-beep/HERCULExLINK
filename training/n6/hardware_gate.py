from __future__ import annotations
"""N6 hardware acceptance gate (Phase N6 §4): structured READY/BLOCKED.

Evaluates the frozen 100M run configuration against measured
hardware. Never trains, never downloads, never modifies state.
Decisions derive from N4 measurements, never guesses.

Usage::

    python -m training.n6.hardware_gate [--target-tokens N] [--max-days N]
"""

import argparse
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Measured N4 evidence (reports/N4_SCALING.md, N4_MEMORY.md).
MEASURED_TOKENS_PER_SEC_100M = 16.7
MEASURED_PEAK_RSS_MB_100M = 3998.0
MEASURED_FREE_MB = 4000.0

# Conservative defaults for the gate itself.
DEFAULT_TARGET_TOKENS = 2_000_000_000   # Chinchilla ~20 tok/param
DEFAULT_MAX_DAYS = 30.0
DEFAULT_MIN_FREE_MB = 6000.0            # weights + ckpt + headroom


def audit_hardware() -> Dict[str, Any]:
    """Actually detected hardware (UNKNOWN where undetectable)."""
    try:
        logical = int(os.cpu_count() or 0)
    except Exception:
        logical = 0
    physical, model, arch = 0, "", platform.machine()
    try:
        import subprocess

        out = subprocess.run(["wmic", "cpu", "get",
                              "Name,NumberOfCores", "/value"],
                             capture_output=True, text=True, timeout=20)
        for line in str(out.stdout or "").splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key == "NumberOfCores" and value.isdigit():
                physical = int(value)
            elif key == "Name" and value:
                model = value
    except Exception:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class Status(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("version", wintypes.DWORD),
                        ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                        ("total_virt", ctypes.c_ulonglong), ("avail_virt", ctypes.c_ulonglong),
                        ("avail_ext", ctypes.c_ulonglong)]

        status = Status()
        status.length = ctypes.sizeof(status)
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        ram_total = int(status.total_phys) if ok else 0
        ram_free = int(status.avail_phys) if ok else 0
    except Exception:
        ram_total = ram_free = 0
    try:
        usage = Path("C:/").stat() if os.name == "nt" else Path("/").stat()
        import shutil

        disk_free = shutil.disk_usage(str(Path.cwd().anchor)).free
    except Exception:
        disk_free = 0
    try:
        import torch  # noqa: F401 (presence probe only)

        torch_present: Optional[str] = getattr(
            __import__("torch"), "__version__", "?")
    except Exception:
        torch_present = None
    cuda, cuda_version, gpu_name, vram = False, "", "", 0
    if torch_present is not None:
        try:
            import torch as _t

            cuda = bool(_t.cuda.is_available())
            if cuda:
                cuda_version = str(_t.version.cuda or "")
                gpu_name = str(_t.cuda.get_device_name(0))
                vram = int(_t.cuda.get_device_properties(0).total_memory)
        except Exception:
            cuda = False
    return {
        "cpu_model": model or "UNKNOWN", "arch": arch,
        "physical_cores": physical, "logical_cores": logical,
        "ram_total_mb": round(ram_total / 1e6, 1),
        "ram_free_mb": round(ram_free / 1e6, 1),
        "disk_free_mb": round(disk_free / 1e6, 1),
        "gpu_name": gpu_name or "NONE", "gpu_count": 1 if cuda else 0,
        "vram_mb": round(vram / 1e6, 1),
        "cuda": cuda, "cuda_version": cuda_version,
        "torch": torch_present or "MISSING",
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
    }


def evaluate_gate(hardware: Dict[str, Any],
                  target_tokens: int = DEFAULT_TARGET_TOKENS,
                  max_days: float = DEFAULT_MAX_DAYS,
                  measured_tok_s: float = MEASURED_TOKENS_PER_SEC_100M,
                  measured_peak_mb: float = MEASURED_PEAK_RSS_MB_100M,
                  measured_free_mb: float = MEASURED_FREE_MB,
                  min_free_mb: float = DEFAULT_MIN_FREE_MB,
                  needs_accelerator: bool = True) -> Dict[str, Any]:
    """Structured gate verdict from detected hardware + N4 evidence.

    ``needs_accelerator`` is False for small configs where CPU
    training is demonstrably practical (no CUDA block); True for
    100M-class and above.
    """
    checks = []
    if needs_accelerator and not hardware.get("cuda"):
        checks.append(("BLOCKED_NO_CUDA", "no CUDA device detected"))
    if hardware.get("ram_free_mb", 0) and hardware["ram_free_mb"] < min_free_mb:
        checks.append(("BLOCKED_INSUFFICIENT_RAM",
                       f"free RAM {hardware['ram_free_mb']} MB < {min_free_mb} MB floor"))
    if measured_peak_mb >= measured_free_mb:
        checks.append(("BLOCKED_INSUFFICIENT_RAM",
                       f"N4 measured 100M peak {measured_peak_mb} MB >= "
                       f"free {measured_free_mb} MB (zero headroom)"))
    days = (target_tokens / measured_tok_s / 86400.0) if measured_tok_s > 0 else float("inf")
    if days > max_days:
        checks.append(("BLOCKED_IMPRACTICAL_TIMELINE",
                       f"{target_tokens:_} tokens at measured {measured_tok_s} tok/s "
                       f"= {days:,.0f} days > {max_days}-day limit"))
    if not checks:
        return {"status": "READY", "checks": [], "target_tokens": target_tokens,
                "estimated_days": round(days, 1)}
    return {"status": "BLOCKED", "checks": checks, "target_tokens": target_tokens,
            "estimated_days": round(days, 1) if days != float("inf") else "infinite",
            "reason": "; ".join(f"{code}: {why}" for code, why in checks)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="n6-hardware-gate")
    parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
    parser.add_argument("--max-days", type=float, default=DEFAULT_MAX_DAYS)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    hardware = audit_hardware()
    verdict = evaluate_gate(hardware, target_tokens=args.target_tokens,
                            max_days=args.max_days)
    report = {"hardware": hardware, "gate": verdict,
              "evidence": "N4 measured 100M: 16.7 tok/s, 3998 MB peak"}
    print(json.dumps(report, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0 if verdict["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
