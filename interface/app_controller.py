from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Application Controller (Stage 9)
Author: Heeran Paul
License: MIT
--------------------------------------------

Thin control/visualization layer over the existing runtime.

UI -> HerculeAppController -> Brain / TaskManager / services.
The controller NEVER executes tools, resolves capabilities, or
bypasses policy: every request flows through ``HerculeCli.handle_line``
(the same entry point as the CLI), and every control flows through
the Brain/TaskManager lifecycle APIs. Unavailable information is
reported as UNKNOWN/UNAVAILABLE, never fabricated.
"""

import threading
import time
from typing import Any, Dict, List, Optional


class HerculeAppController:
    """Bridges the desktop UI and the live HERCULE runtime."""

    def __init__(self, services: Dict[str, Any]):
        # Local import from the boot.py FILE (not the boot/ package,
        # which shadows the module name). boot.py stays importable
        # without tkinter. Frozen-aware: PyInstaller bundles boot.py
        # under sys._MEIPASS, so probe that location first.
        import importlib.util
        import sys
        from pathlib import Path

        candidates = [Path(__file__).resolve().parent.parent / "boot.py"]
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.insert(0, Path(meipass) / "boot.py")
        boot_path = next((p for p in candidates if p.exists()), candidates[-1])
        spec = importlib.util.spec_from_file_location(
            "hercule_boot_cli", str(boot_path))
        boot_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(boot_module)

        self.services = services
        self.brain = services["brain"]
        self.cli = boot_module.HerculeCli(self.brain)
        self._lock = threading.Lock()
        self._busy = False
        self.last_task_id: Optional[str] = None
        self.last_correlation_id: Optional[str] = None
        self.last_result: Optional[Dict[str, Any]] = None
        # Evaluation panel state (v1.1): read-only progress snapshot;
        # attached by an evaluation run, None = no evaluation (honest).
        self.evaluation_state: Optional[Any] = None

    # --------------------------------------------------
    # Conversation / tasks (same path as the CLI)
    # --------------------------------------------------
    def submit(self, text: str) -> Dict[str, Any]:
        """Route one user line through the Brain. Thread-safe, serialized."""
        with self._lock:
            self._busy = True
            try:
                result = self.cli.handle_line(text)
            finally:
                self._busy = False
        if isinstance(result, dict):
            if result.get("task_id"):
                self.last_task_id = result["task_id"]
            if result.get("correlation_id"):
                self.last_correlation_id = result["correlation_id"]
            self.last_result = result
        return result

    def format_response(self, result: Dict[str, Any]) -> str:
        return self.cli.format_response(result)

    @property
    def busy(self) -> bool:
        return self._busy

    # --------------------------------------------------
    # Task controls (Brain/TaskManager lifecycle APIs only)
    # --------------------------------------------------
    def _require_task(self) -> str:
        if not self.last_task_id:
            raise RuntimeError("no active task")
        return self.last_task_id

    def cancel_current(self) -> Dict[str, Any]:
        task_id = self._require_task()
        return {"task_id": task_id, "action": "cancel",
                "result": self.brain.cancel_task(task_id)}

    def pause_current(self) -> Dict[str, Any]:
        task_id = self._require_task()
        return {"task_id": task_id, "action": "pause",
                "result": self.brain.pause_task(task_id)}

    def resume_current(self) -> Dict[str, Any]:
        task_id = self._require_task()
        return {"task_id": task_id, "action": "resume",
                "result": self.brain.resume_task(task_id)}

    # --------------------------------------------------
    # Background autonomy (worker lifecycle + scheduling)
    # --------------------------------------------------
    def autonomy_worker(self):
        """Lazily attach the single autonomy worker (never duplicated)."""
        worker = getattr(self, "_autonomy_worker", None)
        if worker is None:
            from autonomy.worker import AutonomyWorker
            worker = AutonomyWorker(self.services)
            self._autonomy_worker = worker
            try:
                self.services["autonomy_worker"] = worker
            except Exception:
                pass
        return worker

    def shutdown_autonomy(self) -> Dict[str, Any]:
        """Stop the worker cleanly if one was ever attached."""
        worker = getattr(self, "_autonomy_worker", None)
        if worker is None:
            worker = (self.services or {}).get("autonomy_worker")
        if worker is None:
            return {"state": "STOPPED", "note": "never started"}
        try:
            return worker.stop()
        except Exception as exc:
            return {"state": "UNKNOWN", "error": str(exc)[:160]}

    def start_autonomy(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        worker = self.autonomy_worker()
        if config:
            if "enabled" in config:
                worker.set_enabled(bool(config["enabled"]))
            for key in ("poll_interval_s", "max_task_runtime_s",
                        "max_concurrent_tasks"):
                if key in config:
                    try:
                        setattr(worker, key, type(getattr(worker, key))(config[key]))
                    except Exception:
                        pass
        worker.set_enabled(True)
        return worker.start()

    def stop_autonomy(self) -> Dict[str, Any]:
        return self.autonomy_worker().stop()

    def pause_autonomy(self) -> Dict[str, Any]:
        return self.autonomy_worker().pause()

    def resume_autonomy(self) -> Dict[str, Any]:
        return self.autonomy_worker().resume()

    def schedule_task(self, goal: str, delay_s: float = 0.0,
                      interval_s: Optional[float] = None,
                      priority: int = 5, timeout: int = 60,
                      max_retries: int = 2) -> Dict[str, Any]:
        return self.autonomy_worker().schedule(
            goal, delay_s=delay_s, interval_s=interval_s,
            priority=priority, timeout=timeout, max_retries=max_retries)

    def autonomy_snapshot(self) -> Dict[str, Any]:
        try:
            return self.autonomy_worker().status()
        except Exception as exc:
            return {"enabled": False, "worker_state": "UNKNOWN",
                    "error": str(exc)[:160]}

    # --------------------------------------------------
    # Vision panel (v1.1): read-only perception snapshot
    # --------------------------------------------------
    def vision_snapshot(self) -> Dict[str, Any]:
        """Snapshot of visual-perception state for the UI/HUD panel.

        Returns real manager state (READY/ANALYZING/RESULT/UNAVAILABLE),
        never fabricated observations. Analysis itself runs only on
        explicit request (UI button, typed/voice command, ability call).
        """
        try:
            perception = (self.services or {}).get("perception")
            if perception is not None and hasattr(perception, "vision_snapshot"):
                snap = perception.vision_snapshot()
                if isinstance(snap, dict):
                    out = dict(snap)
                    out.setdefault("available", out.get("state") not in ("UNAVAILABLE", "UNKNOWN"))
                    return out
            from perception.vision.manager import VisionManager

            out = VisionManager().snapshot()
            out.setdefault("available", out.get("state") not in ("UNAVAILABLE", "UNKNOWN"))
            return out
        except Exception as exc:
            return {"state": "UNAVAILABLE", "ready": False,
                    "analyzing": False, "has_result": False,
                    "description": "", "confidence": 0.0,
                    "source": "", "model": "",
                    "error": str(exc)[:200], "available": False}

    # --------------------------------------------------
    # Computer panel (v1.2): controlled desktop interaction
    # --------------------------------------------------
    def computer_snapshot(self) -> Dict[str, Any]:
        """Snapshot of computer-use state for the UI/HUD panel.

        Real controller state only (OBSERVING/ACTION_PROPOSED/
        APPROVAL_REQUIRED/EXECUTING/VERIFYING/COMPLETED/FAILED),
        never fabricated actions. The shared controller is process-wide
        so ability executions and UI approvals see the same ledger.
        """
        try:
            from computer.controller import shared_controller

            return shared_controller().snapshot()
        except Exception as exc:
            return {"enabled": False, "state": "UNKNOWN",
                    "current_application": "", "proposed_action": "",
                    "risk": "", "approval": "", "executing": False,
                    "verifying": False, "verified": False,
                    "pending_approvals": [],
                    "history": [], "last_error": str(exc)[:200]}

    def computer_approve(self, request_id: str) -> Dict[str, Any]:
        try:
            from computer.controller import shared_controller

            req = shared_controller().approvals.approve(request_id)
            return {"request_id": req.request_id, "state": req.state}
        except Exception as exc:
            return {"request_id": request_id, "state": "UNKNOWN",
                    "error": str(exc)[:200]}

    def computer_reject(self, request_id: str) -> Dict[str, Any]:
        try:
            from computer.controller import shared_controller

            req = shared_controller().approvals.reject(request_id)
            return {"request_id": req.request_id, "state": req.state}
        except Exception as exc:
            return {"request_id": request_id, "state": "UNKNOWN",
                    "error": str(exc)[:200]}

    def computer_cancel(self) -> Dict[str, Any]:
        try:
            from computer.controller import shared_controller

            return shared_controller().cancel()
        except Exception as exc:
            return {"status": "UNKNOWN", "error": str(exc)[:200]}

    # --------------------------------------------------
    # Reasoning panel (v2 Phase 4): adaptive decision readout
    # --------------------------------------------------
    def reasoning_snapshot(self) -> Dict[str, Any]:
        """Snapshot of the last adaptive reasoning decision.

        Real controller values only (mode/model/budget/latency);
        never hidden reasoning content.
        """
        try:
            decision = dict(getattr(getattr(self, "brain", None),
                                    "last_reasoning", None) or {})
            if not decision:
                return {"mode": "UNKNOWN", "model": "", "provider": "",
                        "reason": "", "budget": {}, "latency_ms": 0.0,
                        "passes": 0}
            budget = decision.get("budget", {}) or {}
            summary = ""
            try:
                tokens = budget.get("max_tokens", "")
                timeout = budget.get("timeout_s", "")
                summary = f"{tokens} tok/{timeout}s/{budget.get('max_passes', '')}pass"
            except Exception:
                summary = ""
            return {"mode": str(decision.get("mode", "UNKNOWN")),
                    "model": str(decision.get("model", ""))[:120],
                    "provider": str(decision.get("provider", "")),
                    "reason": str(decision.get("reason", ""))[:200],
                    "budget": dict(budget), "budget_summary": summary,
                    "latency_ms": float(decision.get("latency_ms", 0.0) or 0.0),
                    "passes": int(decision.get("passes", 0) or 0)}
        except Exception as exc:
            return {"mode": "UNKNOWN", "model": "", "provider": "",
                    "reason": "", "budget": {}, "latency_ms": 0.0,
                    "passes": 0, "error": str(exc)[:200]}

    # --------------------------------------------------
    # Memory panel (v2): read-only memory summary
    # --------------------------------------------------
    def memory_snapshot(self) -> Dict[str, Any]:
        """Snapshot of memory health + recent important memories.

        Real store state only (READY/RECALLING/DEGRADED), never
        private reasoning. RECALLING reflects a recent genuine
        retrieval with its hit count.
        """
        try:
            import time as _time

            memory = (self.services or {}).get("memory")
            if memory is None:
                return {"state": "UNKNOWN", "types": {}, "recent": [],
                        "experience": {}, "recall": {}, "storage": {},
                        "degraded": False}
            try:
                stats = memory.memory_statistics() if hasattr(
                    memory, "memory_statistics") else {}
            except Exception:
                stats = {}
            try:
                recent = memory.history_snapshot(limit=5) if hasattr(
                    memory, "history_snapshot") else []
            except Exception:
                recent = []
            degraded = False
            recall = {}
            try:
                last = getattr(memory, "last_recall", None) or {}
                if last.get("at"):
                    age = _time.time() - float(last["at"])
                    recall = {"query": str(last.get("query", ""))[:80],
                              "count": int(last.get("count", 0)),
                              "recent": age < 5.0}
            except Exception:
                recall = {}
            state = "DEGRADED" if degraded else (
                "RECALLING" if recall.get("recent") else "READY")
            return {"state": state, "types": (stats or {}).get("durable", {}).get("by_type", {}),
                    "recent": [{"content": str(r.get("content", ""))[:100],
                                "memory_type": r.get("memory_type", "")}
                               for r in recent],
                    "recall": recall, "storage": (stats or {}).get("durable", {}),
                    "degraded": degraded}
        except Exception as exc:
            return {"state": "DEGRADED", "types": {}, "recent": [],
                    "experience": {}, "recall": {}, "storage": {},
                    "degraded": True, "error": str(exc)[:200]}

    # --------------------------------------------------
    # World panel (v2): read-only world-model snapshot
    # --------------------------------------------------
    def world_snapshot(self) -> Dict[str, Any]:
        """Snapshot of world-model state for the UI/HUD panel.

        Real repository state only (SYNCED/UPDATING/DEGRADED), never
        the whole database. The world model is context, not authority.
        """
        try:
            world = getattr(getattr(self, "brain", None), "world", None)
            if world is not None and hasattr(world, "snapshot"):
                snap = world.snapshot()
                if isinstance(snap, dict):
                    return snap
            return {"state": "UNKNOWN", "entities": 0, "relationships": 0,
                    "observations": 0, "by_type": {}, "applications": [],
                    "recent": [], "path": "", "degraded": False}
        except Exception as exc:
            return {"state": "DEGRADED", "entities": 0, "relationships": 0,
                    "observations": 0, "by_type": {}, "applications": [],
                    "recent": [], "path": "",
                    "degraded": True, "error": str(exc)[:200]}

    # --------------------------------------------------
    # Evaluation panel (v1.1): read-only progress snapshot
    # --------------------------------------------------
    def evaluation_snapshot(self) -> Dict[str, Any]:
        """Snapshot of the (optional) evaluation run for the UI panel.

        Returns {"available": False} when no evaluation state is
        attached — the UI shows an honest idle state, never fabricated
        progress.
        """
        state = getattr(self, "evaluation_state", None)
        if state is None:
            return {"available": False}
        try:
            snap = dict(state.snapshot())
            snap["available"] = True
            return snap
        except Exception:
            return {"available": False}

    # --------------------------------------------------
    # Decision panel (v2 Phase 5): read-only decision readout
    # --------------------------------------------------
    def decision_snapshot(self) -> Dict[str, Any]:
        """Snapshot of the last Phase-5 strategy decision.

        Real decision-record values only (candidates, selected,
        selection_reason, scores, timing). Never hidden reasoning, never
        fabricated entries: before any cognitive decision this session the
        panel reports an honest idle state.
        """
        try:
            decision = dict(getattr(getattr(self, "brain", None),
                                    "last_decision", None) or {})
            if not decision:
                return {"available": False, "candidates": 0,
                        "selected": "", "reason": ""}
            return {
                "available": True,
                "candidates": int(decision.get("candidates", 0) or 0),
                "valid_candidates": list(decision.get("valid_candidates") or []),
                "rejected_candidates": list(decision.get("rejected_candidates") or []),
                "selected": str(decision.get("selected_strategy", "") or ""),
                "selected_mode": str(decision.get("choice", "") or ""),
                "reason": str(decision.get("selection_reason", "") or "")[:200],
                "scores": {k: round(float(v), 3)
                           for k, v in (decision.get("scores") or {}).items()},
                "decision_time_ms": float(decision.get("decision_time_ms", 0.0) or 0.0),
            }
        except Exception as exc:
            return {"available": False, "candidates": 0,
                    "selected": "", "reason": "", "error": str(exc)[:160]}

    # --------------------------------------------------
    # Read-only snapshot for panels (UNKNOWN, never fabricated)
    # --------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """Full UI snapshot from live runtime state. Never blocks on I/O
        except a bounded model health probe."""
        return {
            "consciousness": self._consciousness(),
            "goals": self._goals(),
            "model": self._model(),
            "task": self._task(),
            "events": self._events(limit=30),
            "busy": bool(getattr(self, "_busy", False)),
            "autonomy": self.autonomy_snapshot(),
            "vision": self.vision_snapshot(),
            "computer": self.computer_snapshot(),
            "world": self.world_snapshot(),
            "memory": self.memory_snapshot(),
            "reasoning": self.reasoning_snapshot(),
            "decision": self.decision_snapshot(),
            "evaluation": self.evaluation_snapshot(),
        }

    def _consciousness(self) -> Dict[str, Any]:
        try:
            consciousness = self.brain.consciousness
            return {
                "state": str(consciousness.get_state()),
                "focus": str(consciousness.current_focus() or "")[:200] or "UNKNOWN",
            }
        except Exception:
            return {"state": "UNKNOWN", "focus": "UNKNOWN"}

    def _goals(self) -> Dict[str, Any]:
        try:
            manager = self.brain.goals
            active = manager.active_goals() or []
            return {
                "active": [{"id": str(g.get("id", "?")),
                            "goal": str(g.get("goal", ""))[:200],
                            "status": str(g.get("status", "UNKNOWN"))}
                           for g in active[:5]],
                "active_count": len(active),
            }
        except Exception:
            return {"active": [], "active_count": 0}

    def _model(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {"provider": "UNKNOWN", "model": "UNKNOWN",
                                "available": False, "health_probe_latency_ms": None,
                                "runtime": "UNKNOWN", "device": "UNKNOWN",
                                "load_time_s": "UNKNOWN",
                                "tokens_per_sec": "UNKNOWN"}
        try:
            manager = self.services.get("models")
            if manager is None:
                return info
            model = str(getattr(manager, "default_model", "") or "") or "UNKNOWN"
            info["model"] = model
            provider = "UNKNOWN"
            available = False
            started = time.perf_counter()
            try:
                router = getattr(manager, "router", None)
                adapters = getattr(router, "adapters", {}) or {}
                # Provider bound to the active model (real values only).
                active = adapters.get("ollama")
                try:
                    name, _ = router.route_by_name(model)
                    active = adapters.get(name, active)
                    provider = name
                except Exception:
                    pass
                if active is not None and hasattr(active, "health"):
                    health = active.health() or {}
                    available = bool(health.get("available", False))
                    if provider == "UNKNOWN":
                        provider = "ollama" if active is adapters.get("ollama") else provider
                    if active is adapters.get("builtin"):
                        provider = "builtin"
                        info["runtime"] = "llama.cpp (managed)"
                        info["device"] = str(health.get("device", "cpu") or "cpu")
                        load = health.get("load_time_s", "")
                        info["load_time_s"] = f"{load}s" if load != "" else "UNKNOWN"
                        tps = health.get("tokens_per_sec", "")
                        info["tokens_per_sec"] = f"{tps} tok/s" if tps != "" else "UNKNOWN"
                    elif active is adapters.get("ollama"):
                        provider = "ollama"
                        info["runtime"] = "ollama server"
                elif adapters:
                    provider = "UNKNOWN"
            except Exception:
                available = False
            info["provider"] = provider
            info["available"] = available
            info["health_probe_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
            return info
        except Exception:
            return info

    def _task(self) -> Optional[Dict[str, Any]]:
        if not self.last_task_id:
            return None
        try:
            orchestrator = self.services.get("orchestrator")
            manager = getattr(orchestrator, "task_manager", None)
            if manager is None:
                return None
            task = manager.get(self.last_task_id)
            if not isinstance(task, dict):
                return None
            metadata = task.get("metadata", {}) or {}
            states = metadata.get("capability_states", {}) or {}
            steps = [{"id": str(sid),
                      "status": str((s or {}).get("status", "UNKNOWN")),
                      "verified": bool(((s or {}).get("verification") or {}).get("passed", False))}
                     for sid, s in sorted(states.items())]
            done = sum(1 for s in steps if s["status"] in ("completed", "COMPLETED"))
            verification = task.get("verification_state", "") or metadata.get("verification_state", "")
            return {
                "id": str(self.last_task_id),
                "goal": str(task.get("goal", metadata.get("goal", "")))[:200] or "UNKNOWN",
                "status": str(task.get("status", "UNKNOWN")),
                "progress": f"{done}/{len(steps)}" if steps else "UNKNOWN",
                "steps": steps,
                "verification": str(verification or "UNKNOWN"),
            }
        except Exception:
            return {"id": str(self.last_task_id), "goal": "UNKNOWN",
                    "status": "UNKNOWN", "progress": "UNKNOWN",
                    "steps": [], "verification": "UNKNOWN"}

    def _events(self, limit: int = 30) -> List[Dict[str, Any]]:
        try:
            tracer = getattr(self.brain, "_tracer", None)
            if tracer is None or not hasattr(tracer, "snapshot"):
                return []
            flat: List[Dict[str, Any]] = []
            for correlation_id, trace in (tracer.snapshot() or {}).items():
                stages = (trace or {}).get("stages", {}) or {}
                for stage, entries in stages.items():
                    for entry in entries or []:
                        flat.append({
                            "at": str((entry or {}).get("timestamp", "")),
                            "stage": str(stage).upper(),
                            "summary": self._summarize(stage, entry),
                            "correlation_id": str(correlation_id)[-8:],
                        })
            flat.sort(key=lambda e: e["at"])
            return flat[-limit:]
        except Exception:
            return []

    @staticmethod
    def _summarize(stage: str, entry: Any) -> str:
        try:
            data = dict(entry or {})
        except Exception:
            return str(entry)[:160]
        data.pop("timestamp", None)
        data.pop("stage", None)
        parts = []
        for key in ("status", "step_id", "ability", "capability", "task_id",
                    "ok", "passed", "outcome", "lesson", "error", "detail",
                    "mode", "steps", "matches", "goal_satisfied"):
            if key in data and data[key] not in (None, "", [], {}):
                value = data[key]
                if isinstance(value, list):
                    value = ",".join(str(v)[:24] for v in value[:4])
                parts.append(f"{key}={str(value)[:80]}")
                if len(parts) >= 3:
                    break
        text = " ".join(parts)
        if not text:
            text = str(data)[:160]
        # Never leak raw prompts/reasoning into the UI stream.
        for banned in ("prompt", "reasoning", "chain-of-thought"):
            if banned in text.lower():
                return f"{stage}: recorded"
        return text[:160]
