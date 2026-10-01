from __future__ import annotations
"""
HERCULE AI Operating System
Module: Resource Quota Manager
Author: Heeran Paul
License: MIT

Per-ability resource quotas: CPU time, memory, disk, network.
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum


class QuotaScope(str, Enum):
    """Scope of quota application."""
    ABILITY = "ability"      # per-ability
    SESSION = "session"      # per-session
    GLOBAL = "global"        # system-wide


@dataclass
class ResourceQuota:
    """Resource limits for an ability/session."""
    max_cpu_seconds: float = 300.0      # total CPU time per window
    max_memory_mb: int = 1024           # peak memory
    max_disk_mb: int = 500              # disk usage
    max_network_mb: int = 100           # network I/O
    max_wall_seconds: float = 600.0     # wall clock time
    max_calls: int = 1000               # API calls
    window_seconds: float = 3600.0      # quota window (1 hour)
    
    # Soft limits (warning only)
    soft_cpu_seconds: Optional[float] = None
    soft_memory_mb: Optional[int] = None
    soft_disk_mb: Optional[int] = None


@dataclass
class QuotaUsage:
    """Current resource usage."""
    cpu_seconds: float = 0.0
    memory_mb: float = 0.0
    disk_mb: float = 0.0
    network_mb: float = 0.0
    wall_seconds: float = 0.0
    calls: int = 0
    window_start: float = field(default_factory=time.time)
    
    def reset_window(self):
        self.cpu_seconds = 0.0
        self.memory_mb = 0.0
        self.disk_mb = 0.0
        self.network_mb = 0.0
        self.wall_seconds = 0.0
        self.calls = 0
        self.window_start = time.time()
    
    def is_expired(self, window_seconds: float) -> bool:
        return (time.time() - self.window_start) >= window_seconds


@dataclass
class QuotaExceeded(Exception):
    """Raised when quota is exceeded."""
    resource: str
    limit: float
    current: float
    scope: str
    
    def __str__(self):
        return f"Quota exceeded: {self.resource} limit {self.limit} exceeded (current: {self.current})"


class ResourceQuotaManager:
    """
    Manages resource quotas per ability/session/global.
    
    Features:
    - Per-ability quotas with configurable limits
    - Rolling time windows
    - Soft limits (warnings) and hard limits (enforcement)
    - Automatic window rollover
    - Usage tracking and reporting
    - Integration with sandbox manager
    """
    
    DEFAULT_QUOTAS: Dict[str, ResourceQuota] = {
        "terminal": ResourceQuota(max_cpu_seconds=60, max_memory_mb=256, max_disk_mb=50, max_wall_seconds=120, max_calls=100),
        "files": ResourceQuota(max_cpu_seconds=30, max_memory_mb=512, max_disk_mb=1000, max_wall_seconds=60, max_calls=500),
        "web": ResourceQuota(max_cpu_seconds=30, max_memory_mb=256, max_disk_mb=100, max_network_mb=50, max_wall_seconds=60, max_calls=100),
        "browser": ResourceQuota(max_cpu_seconds=120, max_memory_mb=1024, max_disk_mb=500, max_network_mb=200, max_wall_seconds=300, max_calls=50),
        "coding": ResourceQuota(max_cpu_seconds=120, max_memory_mb=512, max_disk_mb=500, max_wall_seconds=180, max_calls=200),
        "database": ResourceQuota(max_cpu_seconds=60, max_memory_mb=512, max_disk_mb=1000, max_network_mb=100, max_wall_seconds=120, max_calls=200),
        "package_manager": ResourceQuota(max_cpu_seconds=300, max_memory_mb=1024, max_disk_mb=2000, max_network_mb=500, max_wall_seconds=300, max_calls=50),
        "computer": ResourceQuota(max_cpu_seconds=60, max_memory_mb=512, max_disk_mb=200, max_wall_seconds=120, max_calls=50),
        "default": ResourceQuota(max_cpu_seconds=30, max_memory_mb=256, max_disk_mb=100, max_wall_seconds=60, max_calls=100),
    }
    
    def __init__(self, config_path: Optional[str] = None):
        self.quotas: Dict[str, ResourceQuota] = dict(self.DEFAULT_QUOTAS)
        self.usage: Dict[str, QuotaUsage] = {}
        self._lock = threading.RLock()
        self._callbacks: List[callable] = []
        self.config_path = Path(config_path) if config_path else None
        
        if self.config_path and self.config_path.exists():
            self._load_config()
    
    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            for name, qdata in data.get("quotas", {}).items():
                self.quotas[name] = ResourceQuota(**qdata)
        except Exception:
            pass
    
    def _save_config(self):
        if not self.config_path:
            return
        try:
            data = {"quotas": {name: q.__dict__ for name, q in self.quotas.items()}}
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def set_quota(self, name: str, quota: ResourceQuota):
        """Set quota for an ability."""
        with self._lock:
            self.quotas[name] = quota
        self._save_config()
    
    def get_quota(self, name: str) -> ResourceQuota:
        return self.quotas.get(name, self.DEFAULT_QUOTAS.get("default", ResourceQuota()))
    
    def _get_usage(self, scope: str, scope_id: str) -> QuotaUsage:
        key = f"{scope}:{scope_id}"
        with self._lock:
            if key not in self.usage:
                self.usage[key] = QuotaUsage()
            usage = self.usage[key]
            
            # Check window expiry
            quota = self.get_quota(scope_id)
            if usage.is_expired(quota.window_seconds):
                usage.reset_window()
            return usage
    
    def check_quota(self, scope: str, scope_id: str, resource: str, amount: float = 1) -> bool:
        """Check if quota allows the requested amount."""
        usage = self._get_usage(scope, scope_id)
        quota = self.get_quota(scope_id)
        
        current = getattr(usage, resource.replace('_mb', '').replace('_seconds', ''))
        limit = getattr(quota, resource)
        
        if current + amount > limit:
            return False
        return True
    
    def consume_quota(self, scope: str, scope_id: str, **resources) -> Dict[str, Any]:
        """Consume quota resources. Returns usage info or raises QuotaExceeded."""
        with self._lock:
            usage = self._get_usage(scope, scope_id)
            quota = self.get_quota(scope_id)
            
            # First check all limits
            for resource, amount in resources.items():
                current = getattr(usage, resource.replace('_mb', '').replace('_seconds', ''), 0)
                limit = getattr(quota, resource, float('inf'))
                
                if limit != float('inf') and current + amount > limit:
                    # Check soft limit
                    soft = getattr(quota, f"soft_{resource}", None)
                    if soft and current + amount > soft:
                        self._notify_soft_limit(scope, scope_id, resource, current + amount, soft)
                    
                    if current + amount > limit:
                        raise QuotaExceeded(resource, limit, current + amount, scope)
            
            # Only consume if all checks pass
            for resource, amount in resources.items():
                current = getattr(usage, resource.replace('_mb', '').replace('_seconds', ''), 0)
                setattr(usage, resource.replace('_mb', '').replace('_seconds', ''), current + amount)
            
            return self.get_usage_report(scope, scope_id)

    def check_quota(self, scope: str, scope_id: str, **resources) -> bool:
        """Check if quota allows the requested amount without consuming."""
        usage = self._get_usage(scope, scope_id)
        quota = self.get_quota(scope_id)
        
        for resource, amount in resources.items():
            current = getattr(usage, resource.replace('_mb', '').replace('_seconds', ''), 0)
            limit = getattr(quota, resource, float('inf'))
            
            if limit != float('inf') and current + amount > limit:
                return False
        return True
    
    def _notify_soft_limit(self, scope: str, scope_id: str, resource: str, current: float, soft_limit: float):
        for callback in self._callbacks:
            try:
                callback(scope, scope_id, resource, current, soft_limit)
            except Exception:
                pass
    
    def add_callback(self, callback: callable):
        self._callbacks.append(callback)
    
    def get_usage_report(self, scope: str, scope_id: str) -> Dict[str, Any]:
        usage = self._get_usage(scope, scope_id)
        quota = self.get_quota(scope_id)
        
        return {
            "scope": scope,
            "scope_id": scope_id,
            "usage": {
                "cpu_seconds": usage.cpu_seconds,
                "memory_mb": usage.memory_mb,
                "disk_mb": usage.disk_mb,
                "network_mb": usage.network_mb,
                "wall_seconds": usage.wall_seconds,
                "calls": usage.calls,
            },
            "limits": {
                "cpu_seconds": quota.max_cpu_seconds,
                "memory_mb": quota.max_memory_mb,
                "disk_mb": quota.max_disk_mb,
                "network_mb": quota.max_network_mb,
                "wall_seconds": quota.max_wall_seconds,
                "calls": quota.max_calls,
            },
            "percentages": {
                "cpu_seconds": (usage.cpu_seconds / quota.max_cpu_seconds * 100) if quota.max_cpu_seconds else 0,
                "memory_mb": (usage.memory_mb / quota.max_memory_mb * 100) if quota.max_memory_mb else 0,
                "disk_mb": (usage.disk_mb / quota.max_disk_mb * 100) if quota.max_disk_mb else 0,
                "network_mb": (usage.network_mb / quota.max_network_mb * 100) if quota.max_network_mb else 0,
                "wall_seconds": (usage.wall_seconds / quota.max_wall_seconds * 100) if quota.max_wall_seconds else 0,
                "calls": (usage.calls / quota.max_calls * 100) if quota.max_calls else 0,
            },
            "window_remaining_seconds": max(0, quota.window_seconds - (time.time() - usage.window_start)),
        }
    
    def reset_usage(self, scope: str, scope_id: str):
        key = f"{scope}:{scope_id}"
        with self._lock:
            if key in self.usage:
                self.usage[key].reset_window()
    
    def get_all_usage(self) -> Dict[str, Any]:
        with self._lock:
            return {
                f"{scope}:{scope_id}": self.get_usage_report(scope, scope_id)
                for (scope, scope_id), usage in self.usage.items()
            }


# Integration with AbilityManager
class QuotaEnforcer:
    """Middleware to enforce quotas during ability execution."""
    
    def __init__(self, quota_manager: ResourceQuotaManager):
        self.quota_manager = quota_manager
    
    def check_and_consume(self, ability_name: str, session_id: str = "default") -> Dict[str, Any]:
        """Check and consume quota for an ability call."""
        # First check if quota allows
        if not self.quota_manager.check_quota(
            scope="ability",
            scope_id=ability_name,
            calls=1,
            wall_seconds=1,
        ):
            raise RuntimeError(f"Quota exceeded for {ability_name}")
        
        # Consume
        try:
            return self.quota_manager.consume_quota(
                scope="ability",
                scope_id=ability_name,
                calls=1,
                wall_seconds=1,
            )
        except QuotaExceeded as e:
            raise RuntimeError(f"Quota exceeded for {ability_name}: {e}")
    
    def record_usage(self, ability_name: str, session_id: str = "default", **usage):
        """Record actual resource usage after execution."""
        self.quota_manager.consume_quota(
            scope="ability",
            scope_id=ability_name,
            **usage
        )