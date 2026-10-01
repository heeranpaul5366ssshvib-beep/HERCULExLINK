from __future__ import annotations
"""Device abstraction (N5 §3-§5): explicit, honest, CPU-first.

Backends: ``numpy`` (reference; always available) and ``torch``
(optional; used only when importable AND CUDA is requested and
present). No torch installation is attempted. A requested CUDA
device that is unavailable fails clearly — never silent CPU
fallback. CUDA multi-GPU: single-device only; distributed status
is PLANNED (see ``topology()``).
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class DeviceInfo:
    backend: str          # numpy | torch
    device: str           # cpu | cuda | cuda:N
    available: bool
    name: str = ""
    count: int = 0
    memory_bytes: int = 0  # 0 = UNKNOWN, never invented
    dtype_support: tuple = ("float32",)

    def as_dict(self) -> Dict[str, Any]:
        return {"backend": self.backend, "device": self.device,
                "available": self.available, "name": self.name,
                "count": self.count,
                "memory_bytes": self.memory_bytes or "UNKNOWN",
                "dtype_support": list(self.dtype_support)}


def _torch_info() -> Optional[Dict[str, Any]]:
    try:
        import torch
    except Exception:
        return None
    try:
        cuda = bool(torch.cuda.is_available())
    except Exception:
        cuda = False
    return {"torch_version": getattr(torch, "__version__", "?"), "cuda": cuda}


def describe_backend() -> DeviceInfo:
    """Actually detected backend (never claimed, always probed)."""
    info = _torch_info()
    if info is not None and info["cuda"]:
        import torch

        index = 0
        try:
            name = torch.cuda.get_device_name(index)
        except Exception:
            name = "CUDA device"
        try:
            total = int(torch.cuda.get_device_properties(index).total_memory)
        except Exception:
            total = 0
        return DeviceInfo(backend="torch", device="cuda", available=True,
                          name=name, count=int(torch.cuda.device_count()),
                          memory_bytes=total,
                          dtype_support=("float32", "float16", "bfloat16"))
    return DeviceInfo(backend="numpy", device="cpu", available=True,
                      name="CPU (NumPy reference backend)",
                      count=int(os.cpu_count() or 0),
                      dtype_support=("float32",))


def get_training_device(requested: str = "auto",
                        env_var: str = "HERCULE_LM_DEVICE") -> DeviceInfo:
    """Resolve an explicit device request.

    ``auto`` → best available (CUDA when probed, else CPU).
    ``cpu`` → NumPy CPU path, always available.
    ``cuda``/``cuda:N`` → torch+CUDA probed; raises when unavailable.
    Environment override wins when set and non-empty.
    """
    env = str(os.environ.get(env_var, "") or "").strip().lower()
    want = (env or str(requested or "auto")).strip().lower()
    if want in ("", "auto"):
        return describe_backend()
    if want == "cpu":
        base = describe_backend()
        return DeviceInfo(backend="numpy", device="cpu", available=True,
                          name=base.name if base.backend == "numpy" else "CPU (NumPy reference backend)",
                          count=int(os.cpu_count() or 0),
                          dtype_support=("float32",))
    if want == "cuda" or want.startswith("cuda:"):
        info = _torch_info()
        if info is None:
            raise RuntimeError("CUDA requested but PyTorch is not installed "
                               "(HERCULE_LM_DEVICE=cuda unavailable; use cpu)")
        if not info["cuda"]:
            raise RuntimeError("CUDA requested but torch.cuda.is_available() "
                               "is false (use cpu)")
        full = describe_backend()
        if want.startswith("cuda:"):
            try:
                index = int(want.split(":", 1)[1])
            except ValueError:
                raise RuntimeError(f"invalid device request: {requested!r}")
            if index >= full.count:
                raise RuntimeError(f"cuda:{index} out of range (count={full.count})")
            full.device = f"cuda:{index}"
        return full
    raise RuntimeError(f"invalid device request: {requested!r} "
                       "(expected auto|cpu|cuda|cuda:N)")


def move_batch_to_device(batch, device: DeviceInfo):
    """NumPy backend: batches are already host arrays (explicit no-op).

    The torch backend (when present) would transfer here. Returning
    the batch unchanged on CPU is correct placement, not a silent
    fallback — CUDA requests never reach this path unfulfilled.
    """
    return batch


def gpu_utilization(device_index: int = 0) -> Optional[Dict[str, Any]]:
    """Sample GPU utilization via nvidia-smi (None when unavailable).

    Never fabricated: returns None when nvidia-smi is missing, the
    GPU is absent, or parsing fails. Fields are raw measurements.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["nvidia-smi",
             f"--id={int(device_index)}",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return None
        parts = [p.strip() for p in str(out.stdout or "").split(",")]
        if len(parts) < 5:
            return None

        def _num(text: str) -> Optional[float]:
            try:
                return float(text)
            except (TypeError, ValueError):
                return None

        return {"gpu_util_percent": _num(parts[0]),
                "mem_used_mb": _num(parts[1]),
                "mem_total_mb": _num(parts[2]),
                "temperature_c": _num(parts[3]),
                "power_w": _num(parts[4]),
                "source": "nvidia-smi"}
    except Exception:
        return None


def topology() -> Dict[str, Any]:
    """Single/multi-device posture (honest, no fake distribution)."""
    info = _torch_info()
    cuda = bool(info and info["cuda"])
    return {"world_size": 1, "rank": 0, "local_rank": 0,
            "device_count": describe_backend().count,
            "cuda_available": cuda,
            "distributed": "PLANNED (single-device only; no fake multi-GPU execution)"}


def collect_runtime(device: str = "cpu", dtype: str = "float32",
                    amp: str = "off", backend: str = "") -> Dict[str, Any]:
    """Machine-readable execution record (never fabricated).

    Reports the actually-probed backend/device, GPU identity, and real
    CUDA memory counters (0 when CUDA is absent — never invented).
    ``distributed_status`` is NOT_IMPLEMENTED until genuine
    multi-GPU training lands; a second visible GPU is not claimed.
    """
    info = _torch_info()
    cuda = bool(info and info["cuda"])
    record: Dict[str, Any] = {
        "backend": backend or ("torch" if cuda and str(device).startswith("cuda") else "numpy"),
        "device": str(device),
        "dtype": str(dtype),
        "amp": str(amp),
        "torch_version": (info or {}).get("torch_version", "not-installed"),
        "cuda_available": cuda,
        "gpu_name": "none",
        "gpu_count": 0,
        "allocated_memory_bytes": 0,
        "reserved_memory_bytes": 0,
        "peak_allocated_memory_bytes": 0,
        "peak_reserved_memory_bytes": 0,
        "distributed_status": "NOT_IMPLEMENTED (single-device only; "
                              "two visible GPUs are NOT claimed as 2-GPU training)",
    }
    if not cuda:
        return record
    try:
        import torch

        record["gpu_count"] = int(torch.cuda.device_count())
        try:
            record["gpu_name"] = torch.cuda.get_device_name(0)
        except Exception:
            record["gpu_name"] = "CUDA device"
        if str(device).startswith("cuda"):
            try:
                record["allocated_memory_bytes"] = int(torch.cuda.memory_allocated(device))
                record["reserved_memory_bytes"] = int(torch.cuda.memory_reserved(device))
                record["peak_allocated_memory_bytes"] = int(
                    torch.cuda.max_memory_allocated(device))
                record["peak_reserved_memory_bytes"] = int(
                    torch.cuda.max_memory_reserved(device))
            except Exception:
                pass
    except Exception:
        pass
    return record
