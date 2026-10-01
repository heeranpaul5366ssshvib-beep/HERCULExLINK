from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Resource Snapshot
Author: Heeran Paul
License: MIT
--------------------------------------------

Resource-aware intelligence needs CPU/RAM/disk/concurrency signals
for routing and scheduling. ``psutil`` (already a dependency) is
used when importable; otherwise zeros are reported explicitly —
never fabricated values.
"""

from typing import Any, Dict, Optional

try:  # optional, degrades to explicit zeros
    import psutil as _psutil
except Exception:  # pragma: no cover - environment dependent
    _psutil = None


def resource_snapshot(concurrency: Optional[int] = None) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "cpu_percent": 0.0,
        "ram_percent": 0.0,
        "ram_available_mb": 0.0,
        "disk_percent": 0.0,
        "source": "unavailable",
    }
    if _psutil is not None:
        try:
            snapshot["cpu_percent"] = float(_psutil.cpu_percent(interval=0.0))
            memory = _psutil.virtual_memory()
            snapshot["ram_percent"] = float(memory.percent)
            snapshot["ram_available_mb"] = float(memory.available / (1024 * 1024))
            snapshot["disk_percent"] = float(_psutil.disk_usage("/").percent)
            snapshot["source"] = "psutil"
        except Exception:
            snapshot["source"] = "error"
    if concurrency is not None:
        snapshot["concurrency"] = int(concurrency)
    return snapshot


def under_pressure(snapshot: Dict[str, Any], cpu_limit: float = 90.0, ram_limit: float = 90.0) -> bool:
    """True when measured resources (not defaults) exceed limits."""
    if snapshot.get("source") not in ("psutil",):
        return False
    return float(snapshot.get("cpu_percent", 0.0)) >= cpu_limit or float(snapshot.get("ram_percent", 0.0)) >= ram_limit
