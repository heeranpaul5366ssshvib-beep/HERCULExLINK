from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Central Health Report (v1.0)
Author: Heeran Paul
License: MIT
--------------------------------------------

One honest health report over the live runtime. Every section is
best-effort: unavailable components report UNAVAILABLE with a reason
instead of breaking the report or fabricating values.
"""

from typing import Any, Dict


def _section(name: str, func) -> Dict[str, Any]:
    try:
        detail = func()
        if not isinstance(detail, dict):
            detail = {"value": detail}
        return {"status": "AVAILABLE", **detail}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": str(exc)[:200]}


def health_report(services: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate runtime/brain/model/memory/task/autonomy/ability/
    security/UI health. ``services`` is the RuntimeInitializer dict;
    missing entries yield UNAVAILABLE sections, never exceptions."""
    services = services or {}
    brain = services.get("brain")
    orchestrator = services.get("orchestrator")

    def _brain():
        health = brain.health()
        return {"state": health.get("state", "UNKNOWN"),
                "focus": str(health.get("focus", ""))[:120],
                "active_goals": health.get("active_goals", 0),
                "completed_goals": health.get("completed_goals", 0)}

    def _models():
        manager = services.get("models")
        if manager is None:
            raise RuntimeError("no model service")
        report = manager.discover_models() if hasattr(manager, "discover_models") else {}
        providers = (report or {}).get("providers", {}) or {}
        ollama = providers.get("ollama", {}) if isinstance(providers, dict) else {}
        return {"provider": "ollama" if ollama else "UNKNOWN",
                "default_model": getattr(manager, "default_model", "UNKNOWN"),
                "ollama_available": bool(ollama.get("available", False)),
                "installed_models": (report or {}).get("installed_ollama_models", [])}

    def _memory():
        memory = services.get("memory")
        stats = memory.memory_statistics() if hasattr(memory, "memory_statistics") else memory.health()
        return {"statistics": stats}

    def _tasks():
        manager = getattr(orchestrator, "task_manager", None)
        queue = manager.get_task_queue() if hasattr(manager, "get_task_queue") else []
        counts: Dict[str, int] = {}
        for task in queue:
            key = str((task or {}).get("status", "UNKNOWN")).upper()
            counts[key] = counts.get(key, 0) + 1
        return {"queued_tracked": len(queue), "by_status": counts,
                "store": getattr(manager, "storage_path", "UNKNOWN") or "in-memory"}

    def _autonomy():
        worker = (services or {}).get("autonomy_worker")
        if worker is None:
            return {"status": "AVAILABLE", "worker_state": "STOPPED", "enabled": False,
                    "note": "worker never started"}
        status = worker.status() if hasattr(worker, "status") else {}
        return {"worker_state": status.get("worker_state", "UNKNOWN"),
                "enabled": bool(status.get("enabled", False)),
                "active_task": status.get("active_task", ""),
                "queued": list(status.get("queued", []) or []),
                "last_result": dict(status.get("last_result", {}) or {})}

    def _abilities():
        abilities = getattr(orchestrator, "abilities", None)
        catalog = abilities.describe_all() if hasattr(abilities, "describe_all") else {}
        return {"registered": len(catalog), "names": sorted(catalog)[:50]}

    def _security():
        security = services.get("security")
        if security is None:
            return {"status": "UNAVAILABLE", "reason": "no security service"}
        report = {}
        if hasattr(security, "health"):
            try:
                report = security.health() or {}
            except Exception:
                pass
        policy = getattr(security, "policy", None)
        denied = []
        try:
            permissions = getattr(policy, "permissions", {}) or {}
            denied = sorted(k for k, v in permissions.items() if not v)
        except Exception:
            pass
        return {"detail": report, "explicitly_denied": denied}

    def _ui():
        if not services:
            raise RuntimeError("no services bound; UI has nothing to display")
        return {"mode": "desktop-or-headless (see boot flags)",
                "note": "UI is a read-only view; it never executes tools"}

    report = {
        "runtime": {"state": "ONLINE"},
        "brain": _section("brain", _brain) if brain is not None else {"status": "UNAVAILABLE",
                                                                     "reason": "no brain service"},
        "models": _section("models", _models),
        "memory": _section("memory", _memory),
        "tasks": _section("tasks", _tasks),
        "autonomy": _section("autonomy", _autonomy),
        "abilities": _section("abilities", _abilities),
        "security": _section("security", _security),
        "ui": _section("ui", _ui),
    }
    degraded = [name for name, section in report.items()
                if isinstance(section, dict) and section.get("status") == "UNAVAILABLE"]
    state = "DEGRADED" if degraded else "ONLINE"
    report["runtime"] = {"status": state, "state": state,
                         "unavailable": degraded}
    return report
