#!/usr/bin/env python3
"""Hardware inventory for HERCULE frontier program.

Produces a machine-readable JSON inventory of the current system's
compute capabilities. Never invents unavailable hardware.
"""

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_hardware_inventory() -> dict:
    """Collect all detectable hardware information."""
    import torch

    inventory = {
        "timestamp": _utcnow(),
        "system": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        },
        "cpu": {},
        "memory": {},
        "gpu": {
            "cuda_available": False,
            "torch_version": torch.__version__,
            "cuda_version": getattr(torch.version, "cuda", None),
            "cudnn_version": getattr(torch.backends.cudnn, "version", lambda: None)(),
            "device_count": 0,
            "devices": [],
        },
        "torch": {
            "version": torch.__version__,
            "compiled_cuda_version": getattr(torch.version, "cuda", None),
        },
    }

    # CPU info
    try:
        import psutil
        inventory["cpu"] = {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "max_frequency_mhz": None,
        }
        try:
            freq = psutil.cpu_freq()
            if freq:
                inventory["cpu"]["max_frequency_mhz"] = freq.max
        except Exception:
            pass
    except Exception:
        inventory["cpu"] = {"error": "psutil not available"}

    # Memory info
    try:
        import psutil
        vm = psutil.virtual_memory()
        inventory["memory"] = {
            "total_bytes": vm.total,
            "available_bytes": vm.available,
            "free_bytes": vm.free,
            "used_bytes": vm.used,
            "percent_used": vm.percent,
        }
    except Exception:
        inventory["memory"] = {"error": "psutil not available"}

    # GPU info
    if torch.cuda.is_available():
        inventory["gpu"]["cuda_available"] = True
        inventory["gpu"]["device_count"] = torch.cuda.device_count()
        for i in range(torch.cuda.device_count()):
            try:
                props = torch.cuda.get_device_properties(i)
                device_info = {
                    "index": i,
                    "name": props.name,
                    "total_memory_bytes": props.total_memory,
                    "major": props.major,
                    "minor": props.minor,
                    "multi_processor_count": props.multi_processor_count,
                    "compute_capability": f"{props.major}.{props.minor}",
                }
                inventory["gpu"]["devices"].append(device_info)
            except Exception as e:
                inventory["gpu"]["devices"].append({
                    "index": i,
                    "error": str(e),
                })
    else:
        inventory["gpu"]["devices"] = []

    return inventory


def main():
    out_dir = Path("reports/frontier_program")
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory = collect_hardware_inventory()
    out_file = out_dir / "hardware_inventory.json"
    out_file.write_text(json.dumps(inventory, indent=1), encoding="utf-8")
    print(f"Hardware inventory written to {out_file}")
    print(json.dumps(inventory, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())