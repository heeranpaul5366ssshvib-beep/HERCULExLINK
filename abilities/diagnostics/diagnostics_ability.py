from __future__ import annotations
"""
HERCULE AI Operating System
Module: Diagnostics Ability
Author: Heeran Paul
License: MIT

Real implementation: System diagnostics, health checks, performance monitoring.
"""

import json
import os
import platform
import psutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from abilities.base_ability import BaseAbility


class DiagnosticsAbility(BaseAbility):

    def __init__(self):
        super().__init__(
            "diagnostics",
            "System diagnostics: health, performance, resources, network",
            capability="SYSTEM_OBSERVE",
            inputs={
                "operation": "health|resources|processes|network|disk|services|benchmarks|report",
                "target": "specific process/service name (optional)",
                "duration": "monitoring duration in seconds (default: 5)",
                "interval": "sampling interval in seconds (default: 1)",
            },
            outputs={
                "cpu": "CPU usage, cores, frequency",
                "memory": "RAM usage, swap, available",
                "disk": "disk usage, I/O stats",
                "network": "interfaces, connections, bandwidth",
                "processes": "top processes by CPU/memory",
                "services": "system services status",
                "benchmarks": "performance benchmarks",
            },
            permissions=["SYSTEM_OBSERVE"],
            environments={"default"},
            verification="metrics collected, valid ranges",
            timeout_s=60,
            risk="LOW",
        )

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            op = task.get("operation", "health")
            if op not in ("health", "resources", "processes", "network", "disk", "services", "benchmarks", "report"):
                return f"unknown operation: {op}"
            return ""
        text = str(task or "")
        if not text.strip():
            return "empty diagnostics request"
        return ""

    def execute(self, task, context=None, **kwargs) -> Dict[str, Any]:
        if isinstance(task, dict):
            operation = str(task.get("operation", "health")).lower()
            target = task.get("target")
            duration = int(task.get("duration", 5))
            interval = float(task.get("interval", 1))
        else:
            text = str(task or "").lower()
            if "benchmark" in text:
                operation = "benchmarks"
            elif "process" in text:
                operation = "processes"
            elif "network" in text:
                operation = "network"
            elif "disk" in text:
                operation = "disk"
            elif "service" in text:
                operation = "services"
            elif "resource" in text:
                operation = "resources"
            else:
                operation = "health"
            target = None
            duration = 5
            interval = 1

        try:
            if operation == "health":
                return self._health_check()
            elif operation == "resources":
                return self._resources(duration, interval)
            elif operation == "processes":
                return self._processes(target)
            elif operation == "network":
                return self._network()
            elif operation == "disk":
                return self._disk()
            elif operation == "services":
                return self._services(target)
            elif operation == "benchmarks":
                return self._benchmarks()
            elif operation == "report":
                return self._full_report()
            else:
                return {"status": "failed", "error": f"unknown operation: {operation}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:500]}

    def _health_check(self) -> Dict[str, Any]:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        issues = []
        if cpu > 90:
            issues.append(f"High CPU usage: {cpu}%")
        if mem.percent > 90:
            issues.append(f"High memory usage: {mem.percent}%")
        if disk.percent > 90:
            issues.append(f"High disk usage: {disk.percent}%")
        return {
            "status": "success",
            "operation": "health",
            "healthy": len(issues) == 0,
            "issues": issues,
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "disk_percent": disk.percent,
            "timestamp": time.time(),
        }

    def _resources(self, duration: int, interval: float) -> Dict[str, Any]:
        samples = []
        end = time.time() + duration
        while time.time() < end:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_io_counters()
            net = psutil.net_io_counters()
            samples.append({
                "timestamp": time.time(),
                "cpu_percent": cpu,
                "memory_percent": mem.percent,
                "memory_available_gb": mem.available / (1024**3),
                "disk_read_mb": disk.read_bytes / (1024**2) if disk else 0,
                "disk_write_mb": disk.write_bytes / (1024**2) if disk else 0,
                "net_sent_mb": net.bytes_sent / (1024**2) if net else 0,
                "net_recv_mb": net.bytes_recv / (1024**2) if net else 0,
            })
            time.sleep(interval)
        return {
            "status": "success",
            "operation": "resources",
            "samples": samples,
            "summary": {
                "avg_cpu": sum(s["cpu_percent"] for s in samples) / len(samples),
                "avg_memory": sum(s["memory_percent"] for s in samples) / len(samples),
                "duration": duration,
            },
        }

    def _processes(self, target: Optional[str]) -> Dict[str, Any]:
        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "username", "cmdline"]):
            try:
                info = proc.info
                if target and target.lower() not in (info["name"] or "").lower() and target.lower() not in " ".join(info["cmdline"] or []).lower():
                    continue
                procs.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": info["cpu_percent"],
                    "memory_percent": info["memory_percent"],
                    "username": info["username"],
                    "cmdline": " ".join(info["cmdline"] or [])[:200],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
        return {
            "status": "success",
            "operation": "processes",
            "count": len(procs),
            "processes": procs[:20],
        }

    def _network(self) -> Dict[str, Any]:
        interfaces = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        connections = psutil.net_connections(kind="inet")
        io = psutil.net_io_counters()
        return {
            "status": "success",
            "operation": "network",
            "interfaces": {
                name: [{"address": addr.address, "netmask": addr.netmask, "family": str(addr.family)} for addr in addrs]
                for name, addrs in interfaces.items()
            },
            "stats": {name: {"isup": s.isup, "speed": s.speed, "mtu": s.mtu} for name, s in stats.items()},
            "connections": [
                {"fd": c.fd, "family": str(c.family), "type": str(c.type), "laddr": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "",
                 "raddr": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "", "status": c.status}
                for c in connections[:50]
            ],
            "io": {"bytes_sent": io.bytes_sent, "bytes_recv": io.bytes_recv, "packets_sent": io.packets_sent, "packets_recv": io.packets_recv} if io else {},
        }

    def _disk(self) -> Dict[str, Any]:
        partitions = psutil.disk_partitions()
        usage = {}
        for p in partitions:
            try:
                u = psutil.disk_usage(p.mountpoint)
                usage[p.mountpoint] = {"total_gb": u.total / (1024**3), "used_gb": u.used / (1024**3), "free_gb": u.free / (1024**3), "percent": u.percent}
            except PermissionError:
                pass
        io = psutil.disk_io_counters()
        return {
            "status": "success",
            "operation": "disk",
            "partitions": usage,
            "io": {"read_mb": io.read_bytes / (1024**2), "write_mb": io.write_bytes / (1024**2), "read_count": io.read_count, "write_count": io.write_count} if io else {},
        }

    def _services(self, target: Optional[str]) -> Dict[str, Any]:
        services = []
        try:
            if sys.platform == "win32":
                result = subprocess.run(["sc", "query", "state= all"], capture_output=True, text=True, timeout=10)
                for line in result.stdout.splitlines():
                    if "SERVICE_NAME:" in line:
                        name = line.split(":", 1)[1].strip()
                        if not target or target.lower() in name.lower():
                            services.append({"name": name, "platform": "windows"})
            else:
                result = subprocess.run(["systemctl", "list-units", "--type=service", "--no-legend"], capture_output=True, text=True, timeout=10)
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 4:
                        name = parts[0]
                        if not target or target.lower() in name.lower():
                            services.append({"name": name, "status": parts[2], "sub": parts[3], "platform": "linux"})
        except Exception:
            pass
        return {"status": "success", "operation": "services", "services": services[:50]}

    def _benchmarks(self) -> Dict[str, Any]:
        results = {}
        start = time.perf_counter()
        _ = sum(i * i for i in range(1000000))
        results["cpu_loop_ms"] = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        data = b"x" * (10 * 1024 * 1024)
        _ = hash(data)
        results["hash_10mb_ms"] = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            temp_path = f.name
        try:
            start = time.perf_counter()
            with open(temp_path, "rb") as f:
                _ = f.read()
            results["disk_read_10mb_ms"] = (time.perf_counter() - start) * 1000
        finally:
            Path(temp_path).unlink(missing_ok=True)
        start = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect(("8.8.8.8", 53))
            results["dns_tcp_ms"] = (time.perf_counter() - start) * 1000
        except Exception:
            results["dns_tcp_ms"] = -1
        finally:
            sock.close()
        return {"status": "success", "operation": "benchmarks", "benchmarks": results, "platform": platform.platform(), "python": sys.version}

    def _full_report(self) -> Dict[str, Any]:
        return {
            "status": "success",
            "operation": "report",
            "health": self._health_check(),
            "resources": self._resources(3, 1),
            "processes": self._processes(None),
            "network": self._network(),
            "disk": self._disk(),
            "benchmarks": self._benchmarks(),
        }