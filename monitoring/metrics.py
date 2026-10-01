from __future__ import annotations
"""
HERCULE Monitoring: Metrics and Tracing Export
Author: Heeran Paul
License: MIT

Supports:
- Prometheus metrics export
- OpenTelemetry tracing (optional)
- Structured logging
- Health checks
"""

import logging
import time
import threading
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Generator
from pathlib import Path

try:
    from prometheus_client import Counter, Gauge, Histogram, Summary, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


@dataclass
class MetricSample:
    """Single metric sample."""
    name: str
    value: float
    labels: Dict[str, str]
    timestamp: float = field(default_factory=time.time)
    type: str = "gauge"  # counter, gauge, histogram, summary


class MetricsCollector:
    """
    Central metrics collector with multiple export formats.
    
    Supports:
    - In-memory metrics with labels
    - Prometheus exposition format
    - OpenTelemetry integration
    - Periodic snapshots
    """
    
    def __init__(
        self,
        namespace: str = "hercule",
        enable_prometheus: bool = True,
        enable_otel: bool = False,
        otel_endpoint: Optional[str] = None,
    ):
        self.namespace = namespace
        self._lock = threading.RLock()
        self._metrics: Dict[str, List[MetricSample]] = defaultdict(list)
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        
        # Prometheus
        self._prom_registry: Optional[CollectorRegistry] = None
        self._prom_metrics: Dict[str, Any] = {}
        if enable_prometheus and PROMETHEUS_AVAILABLE:
            self._init_prometheus()
        
        # OpenTelemetry
        self._tracer = None
        if enable_otel and OTEL_AVAILABLE:
            self._init_otel(otel_endpoint)
        
        # System metrics callbacks
        self._system_collectors: List[Callable[[], Dict[str, float]]] = []
    
    def _init_prometheus(self):
        """Initialize Prometheus metrics."""
        self._prom_registry = CollectorRegistry()
        
        # Pre-create common metrics
        self._prom_metrics = {
            "requests_total": Counter(
                "hercule_requests_total",
                "Total requests processed",
                ["ability", "status"],
                registry=self._prom_registry,
            ),
            "request_duration_seconds": Histogram(
                "hercule_request_duration_seconds",
                "Request duration in seconds",
                ["ability", "operation"],
                registry=self._prom_registry,
            ),
            "quota_usage": Gauge(
                "hercule_quota_usage",
                "Current quota usage",
                ["ability", "resource"],
                registry=self._prom_registry,
            ),
            "active_abilities": Gauge(
                "hercule_active_abilities",
                "Currently executing abilities",
                ["ability"],
                registry=self._prom_registry,
            ),
            "memory_usage_bytes": Gauge(
                "hercule_memory_usage_bytes",
                "Memory usage in bytes",
                ["type"],
                registry=self._prom_registry,
            ),
            "audit_logs_total": Counter(
                "hercule_audit_logs_total",
                "Total audit log entries",
                ["outcome"],
                registry=self._prom_registry,
            ),
        }
    
    def _init_otel(self, endpoint: Optional[str]):
        """Initialize OpenTelemetry tracing."""
        provider = TracerProvider(
            resource=Resource.create({"service.name": "hercule"})
        )
        
        if endpoint:
            exporter = OTLPSpanExporter(endpoint=endpoint)
        else:
            exporter = ConsoleSpanExporter()
        
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer("hercule")
    
    def register_system_collector(self, collector: Callable[[], Dict[str, float]]):
        """Register a system metrics collector function."""
        self._system_collectors.append(collector)
    
    # Counter operations
    def increment(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increment a counter."""
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value
            self._record(name, self._counters[key], labels, "counter")
            self._prom_increment(name, value, labels)
    
    def _prom_increment(self, name: str, value: float, labels: Optional[Dict[str, str]]):
        if not self._prom_registry:
            return
        try:
            if name not in self._prom_metrics:
                self._prom_metrics[name] = Counter(
                    f"hercule_{name}",
                    f"Auto-created counter: {name}",
                    list(labels.keys()) if labels else [],
                    registry=self._prom_registry,
                )
            self._prom_metrics[name].labels(**labels or {}).inc(value)
        except Exception:
            pass
    
    # Gauge operations
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge value."""
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
            self._record(name, value, labels, "gauge")
            self._prom_set_gauge(name, value, labels)
    
    def _prom_set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]]):
        if not self._prom_registry:
            return
        try:
            if name not in self._prom_metrics:
                self._prom_metrics[name] = Gauge(
                    f"hercule_{name}",
                    f"Auto-created gauge: {name}",
                    list(labels.keys()) if labels else [],
                    registry=self._prom_registry,
                )
            self._prom_metrics[name].labels(**labels or {}).set(value)
        except Exception:
            pass
    
    # Histogram operations
    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Observe a value for histogram."""
        with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(value)
            self._record(name, value, labels, "histogram")
            self._prom_observe(name, value, labels)
    
    def _prom_observe(self, name: str, value: float, labels: Optional[Dict[str, str]]):
        if not self._prom_registry:
            return
        try:
            if name not in self._prom_metrics:
                self._prom_metrics[name] = Histogram(
                    f"hercule_{name}",
                    f"Auto-created histogram: {name}",
                    list(labels.keys()) if labels else [],
                    registry=self._prom_registry,
                )
            self._prom_metrics[name].labels(**labels or {}).observe(value)
        except Exception:
            pass
    
    @contextmanager
    def timer(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Context manager to time operations."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.observe(name, duration, labels)
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name
    
    def _record(self, name: str, value: float, labels: Optional[Dict[str, str]], type_: str):
        sample = MetricSample(name=name, value=value, labels=labels or {}, type=type_)
        self._metrics[name].append(sample)
        # Keep last 1000 samples per metric
        if len(self._metrics[name]) > 1000:
            self._metrics[name] = self._metrics[name][-1000:]
    
    def collect_system_metrics(self) -> Dict[str, float]:
        """Collect metrics from registered system collectors."""
        result = {}
        for collector in self._system_collectors:
            try:
                result.update(collector())
            except Exception:
                pass
        return result
    
    def get_prometheus_metrics(self) -> bytes:
        """Export metrics in Prometheus format."""
        if not self._prom_registry:
            return b"# Prometheus not available\n"
        
        # Update system metrics
        for name, value in self.collect_system_metrics().items():
            self.set_gauge(f"system_{name}", value)
        
        return generate_latest(self._prom_registry)
    
    def get_prometheus_content_type(self) -> str:
        return CONTENT_TYPE_LATEST if PROMETHEUS_AVAILABLE else "text/plain"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: {"count": len(v), "sum": sum(v), "min": min(v), "max": max(v), "avg": sum(v)/len(v)}
                    for k, v in self._histograms.items() if v
                },
                "metric_names": list(self._metrics.keys()),
            }
    
    def get_tracer(self):
        """Get OpenTelemetry tracer."""
        return self._tracer
    
    @contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Create a tracing span."""
        if self._tracer:
            with self._tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                yield span
        else:
            yield None


class HealthChecker:
    """Health check registry and runner."""
    
    def __init__(self):
        self._checks: Dict[str, Callable[[], tuple[bool, str]]] = {}
    
    def register(self, name: str, check_fn: Callable[[], tuple[bool, str]]):
        """Register a health check.
        
        check_fn should return (healthy: bool, message: str)
        """
        self._checks[name] = check_fn
    
    def run_all(self) -> Dict[str, Any]:
        """Run all health checks."""
        results = {}
        overall = True
        for name, check_fn in self._checks.items():
            try:
                healthy, message = check_fn()
                results[name] = {"healthy": healthy, "message": message}
                if not healthy:
                    overall = False
            except Exception as e:
                results[name] = {"healthy": False, "message": f"Check failed: {e}"}
                overall = False
        return {"overall": overall, "checks": results, "timestamp": time.time()}
    
    def get_json(self) -> str:
        import json
        return json.dumps(self.run_all(), indent=2)


# Global instances
_metrics = MetricsCollector()
_health = HealthChecker()


def get_metrics() -> MetricsCollector:
    return _metrics


def get_health() -> HealthChecker:
    return _health


# Convenience functions
def increment(name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
    _metrics.increment(name, value, labels)


def set_gauge(name: str, value: float, labels: Optional[Dict[str, str]] = None):
    _metrics.set_gauge(name, value, labels)


def observe(name: str, value: float, labels: Optional[Dict[str, str]] = None):
    _metrics.observe(name, value, labels)


def timer(name: str, labels: Optional[Dict[str, str]] = None):
    return _metrics.timer(name, labels)


def span(name: str, attributes: Optional[Dict[str, Any]] = None):
    return _metrics.span(name, attributes)


def get_prometheus_metrics() -> bytes:
    return _metrics.get_prometheus_metrics()


def health_check() -> Dict[str, Any]:
    return _health.run_all()