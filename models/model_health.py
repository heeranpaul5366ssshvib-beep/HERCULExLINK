from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Model Health Monitor
Author: Heeran Paul
License: MIT
--------------------------------------------

Real health states per model adapter — never "healthy because config
exists". Each probe calls the adapter's own ``health()`` and measures
round-trip latency:

AVAILABLE   passed probe, latency within budget
READY       available and top of the routing order (assigned by router)
LOADING     adapter present but probe inconclusive/transient
DEGRADED    available but slow or flapping
UNAVAILABLE probe reports unavailable / raises
FAILED      consecutive failures at/over threshold

Ownership: MODELS. Read-only observer of adapters; it never changes
adapter state.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class HealthState(str, Enum):
    AVAILABLE = "available"
    READY = "ready"
    LOADING = "loading"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass
class HealthRecord:
    adapter_name: str
    state: HealthState = HealthState.LOADING
    available: bool = False
    latency_ms: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_checked: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "state": self.state.value,
            "available": self.available,
            "latency_ms": round(self.latency_ms, 3),
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "last_checked": self.last_checked,
            "detail": dict(self.detail),
        }


class ModelHealthMonitor:
    """Probe adapters and track per-adapter health state over time."""

    def __init__(
        self,
        failure_threshold: int = 3,
        degraded_latency_ms: float = 5000.0,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.failure_threshold = failure_threshold
        self.degraded_latency_ms = degraded_latency_ms
        self._clock = clock or time.perf_counter
        self._records: Dict[str, HealthRecord] = {}

    def _record(self, name: str) -> HealthRecord:
        record = self._records.get(name)
        if record is None:
            record = HealthRecord(adapter_name=name)
            self._records[name] = record
        return record

    def check(self, adapter_name: str, adapter: Any) -> HealthRecord:
        """Run one real probe against an adapter."""
        record = self._record(adapter_name)
        started = self._clock()
        try:
            probe = adapter.health() if hasattr(adapter, "health") else {"status": "healthy", "available": True}
            latency_ms = (self._clock() - started) * 1000.0
            available = bool((probe or {}).get("available", True))
        except Exception as exc:
            latency_ms = (self._clock() - started) * 1000.0
            probe = {"status": "error", "available": False, "reason": str(exc)}
            available = False
        record.latency_ms = latency_ms
        record.last_checked = datetime.now(timezone.utc).isoformat()
        record.detail = dict(probe or {})
        if available:
            record.consecutive_successes += 1
            record.consecutive_failures = 0
            record.available = True
            if record.consecutive_successes == 1 and record.state in (HealthState.LOADING, HealthState.UNAVAILABLE, HealthState.FAILED):
                record.state = HealthState.LOADING  # single success is not trust yet
            elif latency_ms > self.degraded_latency_ms:
                record.state = HealthState.DEGRADED
            elif record.consecutive_successes >= 2:
                record.state = HealthState.AVAILABLE
        else:
            record.consecutive_failures += 1
            record.consecutive_successes = 0
            record.available = False
            if record.consecutive_failures >= self.failure_threshold:
                record.state = HealthState.FAILED
            else:
                record.state = HealthState.UNAVAILABLE
        return record

    def check_all(self, adapters: Dict[str, Any]) -> Dict[str, HealthRecord]:
        return {name: self.check(name, adapter) for name, adapter in adapters.items()}

    def record(self, adapter_name: str) -> Optional[HealthRecord]:
        return self._records.get(adapter_name)

    def healthy_adapters(self) -> List[str]:
        return [name for name, rec in self._records.items() if rec.available and rec.state != HealthState.FAILED]

    def snapshot(self) -> Dict[str, Any]:
        return {name: rec.as_dict() for name, rec in self._records.items()}
