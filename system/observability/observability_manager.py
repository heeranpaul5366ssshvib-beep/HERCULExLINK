from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List


class ObservabilityManager:
    """Structured logs, metrics, and task traces with correlation tracking."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.metrics: Dict[str, float] = {}
        self.traces: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def log_event(self, event_type: str, payload: Dict[str, Any] | None = None, latency_ms: int | None = None, correlation_id: str | None = None) -> str:
        event_id = f"event-{len(self.events) + 1}"
        data = {
            "id": event_id,
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
            "latency_ms": latency_ms,
            "correlation_id": correlation_id or payload.get("correlation_id") if isinstance(payload, dict) else None,
        }
        self.events.append(data)
        return event_id

    def record_metric(self, name: str, value: float):
        self.metrics[name] = value
        return self.metrics[name]

    def trace(self, correlation_id: str, event: Dict[str, Any]):
        self.traces[correlation_id].append(event)

    def snapshot(self):
        return {
            "event_count": len(self.events),
            "metrics": dict(self.metrics),
            "traces": {k: list(v) for k, v in self.traces.items()},
            "events": list(self.events),
        }
