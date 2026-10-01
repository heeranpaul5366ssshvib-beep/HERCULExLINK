from __future__ import annotations
"""Monitoring + failure classification + retry policy (spec §7/§8)."""

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from tools.kaggle_trainer import kaggle_executor as _kx

TRANSIENT = {"quota", "accelerator", "timeout", "transient"}
TERMINAL = {"code", "config", "data", "auth"}


def parse_progress(log_text: str) -> Dict[str, Any]:
    """Extract latest step/loss/tok/s + GPU/VRAM lines from run.log."""
    step = loss = toks = vram = gpu = None
    for line in (log_text or "").splitlines():
        m = re.match(r"step=(\d+)/\d+\s+loss=([\d.]+).*?([\d.]+)tok/s", line)
        if m:
            step, loss, toks = int(m.group(1)), float(m.group(2)), float(m.group(3))
        m2 = re.search(r"gpu=(\S.*?)\s+count=(\d+)", line)
        if m2:
            gpu = f"{m2.group(1)} x{m2.group(2)}"
        m3 = re.search(r"peak_vram_bytes=(\d+)", line)
        if m3:
            vram = int(m3.group(1))
    return {"step": step, "loss": loss, "tok_s": toks, "gpu": gpu,
            "peak_vram_bytes": vram}


def classify_failure(status: str, log_text: str) -> Dict[str, Any]:
    """Map status + log tail to a failure class (never guess blindly)."""
    text = f"{status}\n{log_text or ''}".lower()
    if "quota" in text or "limit" in text and "gpu" in text:
        return {"class": "quota", "transient": True}
    if "no_cuda" in text or "accelerator" in text or "gpu" in text and "unavailable" in text:
        return {"class": "accelerator", "transient": True}
    if ("out_of_memory" in text or "out of memory" in text
            or "outofmemory" in text or "cuda oom" in text):
        return {"class": "oom", "transient": False,
                "hint": "reduce --batch/--seq-len or enable grad-accum"}
    if "no_dataset" in text or "dataset" in text and "error" in text:
        return {"class": "data", "transient": False}
    if "checkpoin" in text and ("error" in text or "corrupt" in text):
        return {"class": "checkpoint", "transient": False}
    if "timeout" in text or "timed out" in text or "deadline" in text:
        return {"class": "timeout", "transient": True}
    if "remote_fail" in text or "traceback" in text or "error" in text:
        return {"class": "code", "transient": False}
    if status.strip().lower() not in ("complete", "success", ""):
        return {"class": "unknown", "transient": False}
    return {"class": "none", "transient": False}


def poll_status(kernel_id: str, timeout_s: float = 3600.0,
                interval_s: float = 60.0,
                on_tick: Optional[Callable[[Dict[str, Any]], None]] = None,
                fetch_logs: Optional[Callable[[], str]] = None) -> Dict[str, Any]:
    """Poll until terminal state. Returns final record (never hangs forever)."""
    t0 = time.perf_counter()
    last: Dict[str, Any] = {"state": "unknown"}
    while time.perf_counter() - t0 < timeout_s:
        res = _kx.kernels_status(kernel_id)
        state = "unknown"
        for line in (res.get("output", "") or "").splitlines():
            if "status" in line.lower():
                state = line.strip()[-40:]
                break
        last = {"state": state, "raw": res.get("output", "")[-2000:],
                "elapsed_s": round(time.perf_counter() - t0, 1)}
        progress: Dict[str, Any] = {}
        if fetch_logs is not None:
            try:
                progress = parse_progress(fetch_logs())
            except Exception:
                pass
        last["progress"] = progress
        if on_tick is not None:
            try:
                on_tick(last)
            except Exception:
                pass
        low = state.lower()
        if any(k in low for k in ("complete", "success", "error", "fail", "cancel")):
            last["terminal"] = True
            return last
        time.sleep(interval_s)
    last["terminal"] = False
    last["timeout"] = True
    return last


def should_retry(failure: Dict[str, Any], attempts: int,
                 max_retries: int = 2) -> Dict[str, Any]:
    """Retry transient failures only, bounded. Deterministic code errors: never."""
    if attempts >= max_retries:
        return {"retry": False, "reason": "retry budget exhausted"}
    if failure.get("class") in ("code", "data", "checkpoint"):
        return {"retry": False,
                "reason": f"deterministic {failure.get('class')} failure: fix, do not retry"}
    if failure.get("transient"):
        return {"retry": True,
                "reason": f"transient {failure.get('class')} failure"}
    return {"retry": False, "reason": "non-transient failure"}
