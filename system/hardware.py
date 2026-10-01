from __future__ import annotations
"""HERCULE PC-Frontier: Hardware Detection and Runtime Profiles.

Detects available CPU, RAM, GPU, VRAM, OS, disk, thread count.
Selects appropriate runtime profile automatically: ULTRA_LOW, LOW, BALANCED, HIGH.
"""

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class RuntimeProfile(str, Enum):
    """Hardware-aware runtime profiles."""
    ULTRA_LOW = "ultra_low"
    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"


@dataclass
class CPUInfo:
    model: str = "UNKNOWN"
    physical_cores: int = 0
    logical_cores: int = 0
    max_frequency_mhz: Optional[float] = None
    architecture: str = ""


@dataclass
class MemoryInfo:
    total_bytes: int = 0
    available_bytes: int = 0
    free_bytes: int = 0
    used_bytes: int = 0
    percent_used: float = 0.0
    total_mb: float = 0.0
    available_mb: float = 0.0


@dataclass
class GPUInfo:
    cuda_available: bool = False
    device_count: int = 0
    devices: List[Dict[str, Any]] = field(default_factory=list)
    total_vram_bytes: int = 0
    total_vram_mb: float = 0.0
    primary_device_name: str = "NONE"


@dataclass
class DiskInfo:
    free_bytes: int = 0
    total_bytes: int = 0
    free_mb: float = 0.0


@dataclass
class HardwareInventory:
    """Complete hardware inventory for the current system."""
    timestamp: str = ""
    system: Dict[str, Any] = field(default_factory=dict)
    cpu: CPUInfo = field(default_factory=CPUInfo)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    gpu: GPUInfo = field(default_factory=GPUInfo)
    disk: DiskInfo = field(default_factory=DiskInfo)
    profile: RuntimeProfile = RuntimeProfile.BALANCED
    torch_version: Optional[str] = None
    cuda_version: Optional[str] = None


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _get_cpu_info() -> CPUInfo:
    """Detect CPU information."""
    cpu = CPUInfo()
    cpu.architecture = platform.machine()
    
    try:
        cpu.logical_cores = os.cpu_count() or 0
    except Exception:
        cpu.logical_cores = 0
    
    # Try to get physical cores and model name on Windows
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["wmic", "cpu", "get", "Name,NumberOfCores,MaxClockSpeed", "/value"],
                capture_output=True, text=True, timeout=10
            )
            for line in (out.stdout or "").splitlines():
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key == "NumberOfCores" and value.isdigit():
                    cpu.physical_cores = int(value)
                elif key == "Name" and value:
                    cpu.model = value
                elif key == "MaxClockSpeed" and value.isdigit():
                    cpu.max_frequency_mhz = float(value)
        except Exception:
            pass
    
    # Fallback: use logical cores if physical not detected
    if cpu.physical_cores == 0 and cpu.logical_cores > 0:
        cpu.physical_cores = max(1, cpu.logical_cores // 2)
    
    # Linux fallback
    if sys.platform == "linux" and cpu.physical_cores == 0:
        try:
            with open("/proc/cpuinfo", "r") as f:
                content = f.read()
            physical_ids = set()
            for line in content.splitlines():
                if line.startswith("physical id"):
                    physical_ids.add(line.split(":")[1].strip())
            cpu.physical_cores = len(physical_ids) or cpu.logical_cores
            # Get model name
            for line in content.splitlines():
                if line.startswith("model name"):
                    cpu.model = line.split(":")[1].strip()
                    break
        except Exception:
            pass
    
    return cpu


def _get_memory_info() -> MemoryInfo:
    """Detect memory information."""
    mem = MemoryInfo()
    
    try:
        import psutil
        vm = psutil.virtual_memory()
        mem.total_bytes = vm.total
        mem.available_bytes = vm.available
        mem.free_bytes = vm.free
        mem.used_bytes = vm.used
        mem.percent_used = vm.percent
        mem.total_mb = round(vm.total / 1e6, 1)
        mem.available_mb = round(vm.available / 1e6, 1)
    except Exception:
        # Windows API fallback
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                
                class Status(ctypes.Structure):
                    _fields_ = [
                        ("length", wintypes.DWORD),
                        ("version", wintypes.DWORD),
                        ("total_phys", ctypes.c_ulonglong),
                        ("avail_phys", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong),
                        ("avail_page", ctypes.c_ulonglong),
                        ("total_virt", ctypes.c_ulonglong),
                        ("avail_virt", ctypes.c_ulonglong),
                        ("avail_ext", ctypes.c_ulonglong),
                    ]
                
                status = Status()
                status.length = ctypes.sizeof(status)
                ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
                if ok:
                    mem.total_bytes = int(status.total_phys)
                    mem.available_bytes = int(status.avail_phys)
                    mem.free_bytes = int(status.avail_phys)
                    mem.used_bytes = int(status.total_phys - status.avail_phys)
                    mem.percent_used = (mem.used_bytes / mem.total_bytes * 100) if mem.total_bytes > 0 else 0
                    mem.total_mb = round(mem.total_bytes / 1e6, 1)
                    mem.available_mb = round(mem.available_bytes / 1e6, 1)
            except Exception:
                pass
    
    return mem


def _get_gpu_info() -> GPUInfo:
    """Detect GPU information via PyTorch (optional, lazy)."""
    gpu = GPUInfo()
    
    # Skip torch import by default for speed - only check if explicitly needed
    # Torch import can be very slow on some systems
    try:
        # Try a quick check without full import
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", "import torch; print(torch.cuda.is_available())"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and "True" in result.stdout:
            # Torch available and CUDA works - do full detection
            import torch
            gpu.torch_version = torch.__version__
            gpu.cuda_version = getattr(torch.version, "cuda", None)
            gpu.cuda_available = True
            gpu.device_count = torch.cuda.device_count()
            total_vram = 0
            for i in range(gpu.device_count):
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
                    gpu.devices.append(device_info)
                    total_vram += props.total_memory
                    if i == 0:
                        gpu.primary_device_name = props.name
                except Exception as e:
                    gpu.devices.append({"index": i, "error": str(e)})
            gpu.total_vram_bytes = total_vram
            gpu.total_vram_mb = round(total_vram / 1e6, 1)
    except Exception:
        pass
    
    return gpu


def _get_disk_info() -> DiskInfo:
    """Detect disk information."""
    disk = DiskInfo()
    
    try:
        usage = shutil.disk_usage(str(Path.cwd().anchor))
        disk.total_bytes = usage.total
        disk.free_bytes = usage.free
        disk.free_mb = round(usage.free / 1e6, 1)
    except Exception:
        pass
    
    return disk


def collect_hardware_inventory() -> HardwareInventory:
    """Collect complete hardware inventory."""
    inventory = HardwareInventory()
    inventory.timestamp = _utcnow()
    inventory.system = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
    }
    inventory.cpu = _get_cpu_info()
    inventory.memory = _get_memory_info()
    inventory.gpu = _get_gpu_info()
    inventory.disk = _get_disk_info()
    
    # Determine runtime profile
    inventory.profile = select_runtime_profile(inventory)
    
    return inventory


def select_runtime_profile(inventory: HardwareInventory) -> RuntimeProfile:
    """Select runtime profile based on hardware capabilities."""
    
    # Check for GPU with sufficient VRAM
    has_gpu = inventory.gpu.cuda_available and inventory.gpu.total_vram_mb >= 4000
    
    # Available RAM in MB
    ram_mb = inventory.memory.available_mb
    
    # CPU cores
    cores = inventory.cpu.logical_cores or 1
    
    # Profile selection logic
    if has_gpu and inventory.gpu.total_vram_mb >= 8000 and ram_mb >= 8000 and cores >= 8:
        return RuntimeProfile.HIGH
    elif has_gpu and inventory.gpu.total_vram_mb >= 4000 and ram_mb >= 4000 and cores >= 4:
        return RuntimeProfile.BALANCED
    elif ram_mb >= 2000 and cores >= 2:
        return RuntimeProfile.LOW
    else:
        return RuntimeProfile.ULTRA_LOW


def get_profile_config(profile: RuntimeProfile) -> Dict[str, Any]:
    """Get configuration parameters for a runtime profile."""
    
    configs = {
        RuntimeProfile.ULTRA_LOW: {
            "max_model_params": 200_000_000,      # 200M params max (allows 100M native)
            "max_context_tokens": 1024,
            "batch_size": 1,
            "num_threads": 1,
            "use_kv_cache": True,
            "use_quantization": True,
            "enable_streaming": True,
            "prefer_native_lm": True,
            "allow_external_models": False,
            "memory_limit_mb": 512,
            "verification_required": True,
        },
        RuntimeProfile.LOW: {
            "max_model_params": 50_000_000,      # 50M params max
            "max_context_tokens": 2048,
            "batch_size": 1,
            "num_threads": 2,
            "use_kv_cache": True,
            "use_quantization": True,
            "enable_streaming": True,
            "prefer_native_lm": True,
            "allow_external_models": True,
            "memory_limit_mb": 1024,
            "verification_required": True,
        },
        RuntimeProfile.BALANCED: {
            "max_model_params": 200_000_000,     # 200M params max
            "max_context_tokens": 4096,
            "batch_size": 2,
            "num_threads": 4,
            "use_kv_cache": True,
            "use_quantization": False,
            "enable_streaming": True,
            "prefer_native_lm": False,
            "allow_external_models": True,
            "memory_limit_mb": 4096,
            "verification_required": True,
        },
        RuntimeProfile.HIGH: {
            "max_model_params": 1_000_000_000,   # 1B params max
            "max_context_tokens": 8192,
            "batch_size": 4,
            "num_threads": 8,
            "use_kv_cache": True,
            "use_quantization": False,
            "enable_streaming": True,
            "prefer_native_lm": False,
            "allow_external_models": True,
            "memory_limit_mb": 8192,
            "verification_required": True,
        },
    }
    
    return configs.get(profile, configs[RuntimeProfile.BALANCED])


def estimate_model_memory(params: int, quantized: bool = False, context_tokens: int = 2048) -> float:
    """Estimate model memory usage in MB.
    
    Args:
        params: Number of parameters
        quantized: Whether model is quantized (4-bit)
        context_tokens: Context window size for KV cache
        
    Returns:
        Estimated memory in MB
    """
    # Base model weights: params * 4 bytes (float32) or params * 0.5 bytes (4-bit)
    if quantized:
        weights_mb = params * 0.5 / 1e6
    else:
        weights_mb = params * 4 / 1e6
    
    # KV cache estimate (more realistic):
    # For a transformer: 2 * num_layers * num_heads * head_dim * context * 2 bytes (fp16)
    # Typical ratios: hidden_size ~ sqrt(params * 4/3), num_layers ~ 12-24, head_dim = hidden_size/num_heads
    # Simplified: KV cache ~= 0.5 * weights_mb * (context_tokens / 2048) for typical models
    kv_cache_mb = weights_mb * 0.5 * (context_tokens / 2048)
    
    # Overhead for activations, etc. (10-20% of weights)
    overhead_mb = weights_mb * 0.15
    
    return weights_mb + kv_cache_mb + overhead_mb


def can_load_model(params: int, profile: RuntimeProfile, quantized: bool = False) -> bool:
    """Check if a model can be loaded within profile constraints."""
    config = get_profile_config(profile)
    estimated_mb = estimate_model_memory(params, quantized, config["max_context_tokens"])
    return estimated_mb <= config["memory_limit_mb"]


def get_optimal_thread_count(profile: RuntimeProfile) -> int:
    """Get optimal thread count for the profile."""
    config = get_profile_config(profile)
    return min(config["num_threads"], os.cpu_count() or 1)


# Global hardware inventory (lazy loaded)
_hardware_inventory: Optional[HardwareInventory] = None


def get_hardware_inventory() -> HardwareInventory:
    """Get cached hardware inventory, collecting if needed."""
    global _hardware_inventory
    if _hardware_inventory is None:
        _hardware_inventory = collect_hardware_inventory()
    return _hardware_inventory


def get_runtime_profile() -> RuntimeProfile:
    """Get the current runtime profile."""
    return get_hardware_inventory().profile


def get_profile_config_current() -> Dict[str, Any]:
    """Get configuration for the current runtime profile."""
    return get_profile_config(get_runtime_profile())


def print_hardware_summary() -> None:
    """Print a human-readable hardware summary."""
    inv = get_hardware_inventory()
    config = get_profile_config(inv.profile)
    
    print(f"\n{'='*60}")
    print(f"HERCULE PC-FRONTIER HARDWARE SUMMARY")
    print(f"{'='*60}")
    print(f"Profile: {inv.profile.value.upper()}")
    print(f"Timestamp: {inv.timestamp}")
    print(f"\nSystem: {inv.system['system']} {inv.system['release']} ({inv.system['machine']})")
    print(f"Python: {inv.system['python_version']}")
    
    print(f"\nCPU: {inv.cpu.model}")
    print(f"  Cores: {inv.cpu.physical_cores} physical / {inv.cpu.logical_cores} logical")
    if inv.cpu.max_frequency_mhz:
        print(f"  Max Frequency: {inv.cpu.max_frequency_mhz:.0f} MHz")
    
    print(f"\nMemory:")
    print(f"  Total: {inv.memory.total_mb:.0f} MB")
    print(f"  Available: {inv.memory.available_mb:.0f} MB ({100-inv.memory.percent_used:.1f}% free)")
    
    print(f"\nGPU:")
    if inv.gpu.cuda_available:
        print(f"  CUDA: Available (v{inv.gpu.cuda_version})")
        print(f"  Devices: {inv.gpu.device_count}")
        for dev in inv.gpu.devices:
            if "name" in dev:
                print(f"    [{dev['index']}] {dev['name']} - {dev['total_memory_bytes']/1e9:.1f} GB VRAM")
        print(f"  Total VRAM: {inv.gpu.total_vram_mb:.0f} MB")
    else:
        print(f"  CUDA: Not available")
    
    print(f"\nDisk:")
    print(f"  Free: {inv.disk.free_mb:.0f} MB")
    
    print(f"\nProfile Config ({inv.profile.value}):")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print_hardware_summary()