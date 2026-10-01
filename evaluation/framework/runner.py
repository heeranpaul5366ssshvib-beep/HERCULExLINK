from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Runner
Author: Heeran Paul
License: MIT
--------------------------------------------

Benchmark Task -> Evaluation Runner -> HERCULE -> Observed Result ->
Scoring -> Evaluation Report.

The runner drives the REAL pipeline through an adapter (Brain.think /
Brain.run_cycle): it never reimplements planning, capability
resolution, policy or execution. Agentic tasks flow through the same
Brain path as user requests. Timeout / error / skip outcomes are
observed, recorded honestly, never fabricated.
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from evaluation.framework.adapters import EvalAdapter
from evaluation.framework.config import EvalConfig
from evaluation.framework.result import (Outcome, StageTiming, SuiteRun,
                                         TaskResult, new_run_id, save_run,
                                         utc_now_iso)
from evaluation.framework.sandbox import run_code_in_sandbox
from evaluation.framework.scoring import score_task
from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod
from evaluation.framework.version import app_version


class _TaskTimeout(Exception):
    pass


def _run_with_timeout(fn: Callable[[], Any], timeout_s: float) -> Any:
    """Run one task in a worker thread with a hard timeout.

    Threads cannot be killed, so on timeout we abandon the worker and
    report TIMEOUT honestly; the abandoned call may still finish in the
    background, but its result is discarded.
    """
    from concurrent.futures import TimeoutError as FutureTimeout

    box: Dict[str, Any] = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - recorded as task error
            box["error"] = exc

    worker = ThreadPoolExecutor(max_workers=1)
    try:
        future = worker.submit(target)
        try:
            future.result(timeout=max(1.0, float(timeout_s)))
        except FutureTimeout:
            raise _TaskTimeout() from None
    finally:
        worker.shutdown(wait=False)
    if "error" in box:
        raise box["error"]
    if "value" not in box:
        raise _TaskTimeout()
    return box["value"]


class EvaluationRunner:
    """Executes suites against one adapter and produces a SuiteRun."""

    def __init__(self, adapter: EvalAdapter, config: Optional[EvalConfig] = None):
        self.adapter = adapter
        self.config = (config or EvalConfig()).sanitized()
        self._lock = threading.Lock()  # serializes ACTIVE/sandboxed tasks
        self.on_task_done = None       # optional callback(TaskResult) for UI/HUD

    # --------------------------------------------------
    # Task execution
    # --------------------------------------------------
    def _observed_for(self, task: EvalTask) -> Any:
        """Route the task through the real HERCULE entry points."""
        if task.extras.get("classification"):
            # Phase 3 routing probes: HERCULE's deterministic request
            # router classifies the embedded transcript — no model call.
            return self.adapter.classify(str(task.extras.get("transcript", task.prompt)))
        if str(task.extras.get("probe", "")) == "memory_probe":
            return self._memory_probe(task)
        if isinstance(task.extras.get("ability_eval"), dict):
            return self._ability_eval(task)
        if task.autonomy_level is not None:
            # UAI Phase M: the real autonomy gate judges first; denied
            # goals never reach the pipeline (REQUEST -> GATE -> DENY).
            from autonomy.levels import evaluate_gate

            gate = evaluate_gate(task.autonomy_level, task.prompt)
            if not gate.get("allowed", False):
                return {"status": "failed", "error": gate.get("reason", ""),
                        "result": {"completed": [], "failed": []},
                        "verification": {"passed_steps": 0, "failed_steps": []},
                        "replans": 0, "autonomy_gate": gate}
        if task.category == EvalCategory.AGENTIC or task.category == EvalCategory.HERCULE_INTERNAL \
                or task.safety_class == SafetyClass.ACTIVE:
            return self.adapter.run_goal(task.prompt)
        return self.adapter.think(task.prompt)

    def _ability_eval(self, task: EvalTask) -> Dict[str, Any]:
        """Execute one ability through AbilityManager (real policy /
        capability / environment / input validation path). Used for
        research-evidence tasks; fixtures from task.extras (sources,
        denials) are already applied by the caller window.
        """
        spec = task.extras.get("ability_eval") or {}
        services = getattr(self.adapter, "services", None) or {}
        try:
            abilities = getattr(services.get("orchestrator"), "abilities", None)
            if abilities is None:
                return {"status": "error", "error": "abilities unavailable"}
            if hasattr(abilities, "ensure_defaults"):
                abilities.ensure_defaults()
            out = abilities.execute(
                str(spec.get("ability", "")),
                str(spec.get("task", task.prompt)),
                capabilities=list(spec.get("capabilities") or []))
            return out if isinstance(out, dict) else {"status": "error",
                                                      "error": "non-dict ability result"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300],
                    "verification_status": "unverified", "evidence": []}

    def _memory_probe(self, task: EvalTask) -> Dict[str, Any]:
        """Deterministic MemoryManager store/recall probe (Phase 3)."""
        memory = getattr(self.adapter, "memory", None)
        if memory is None:
            return {"status": "error", "error": "memory unavailable"}
        topic = str(task.extras.get("topic", ""))
        operation = str(task.extras.get("operation", "recall"))
        try:
            if operation == "store_then_recall":
                memory.remember_fact(topic, str(task.extras.get("value", "")))
            fact = memory.recall_fact(topic)
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:200]}
        value = ""
        if isinstance(fact, dict):
            value = str(fact.get("information", "") or fact.get("value", "") or "")
        elif fact is not None:
            value = str(fact)
        return {"status": "ok", "value": value or "UNKNOWN"}

    def _score_observed(self, task: EvalTask, observed: Any) -> float:
        if task.scoring_method == ScoringMethod.CODE_PASS:
            code = self._extract_code(observed)
            tests = list((task.expected or {}).get("tests", [])) if isinstance(task.expected, dict) else []
            if not code:
                return 0.0
            outcome = run_code_in_sandbox(code, tests, timeout_s=min(20.0, task.timeout_s))
            if not outcome.get("compiled") or not tests:
                return 0.0
            return round(outcome.get("passed", 0) / len(tests), 3)
        return score_task(observed, task.expected, task.scoring_method.value)

    @staticmethod
    def _extract_code(observed: Any) -> str:
        import re
        text = observed if isinstance(observed, str) else json.dumps(observed)
        match = re.search(r"```(?:python)?\s*(.*?)```", str(text or ""), re.DOTALL)
        if match:
            return match.group(1).strip()
        lines = str(text or "").strip().splitlines()
        code_lines = [ln for ln in lines if ("def " in ln or "return" in ln or "=" in ln)]
        return "\n".join(code_lines).strip()

    def run_task(self, task: EvalTask, run_index: int = 1) -> TaskResult:
        started = time.perf_counter()
        result = TaskResult(
            task_id=(task.task_id if run_index <= 1 else f"{task.task_id}#r{run_index}"),
            suite_id=task.suite,
            category=task.category.value, outcome=Outcome.ERROR,
            expected=(task.expected if isinstance(task.expected, (str, int, float, list)) else
                      (task.expected.get("answer") if isinstance(task.expected, dict) else None)),
            model=self.adapter.default_model(), provider=self.adapter.default_provider(),
            safety_class=task.safety_class.value)
        if task.safety_class == SafetyClass.SANDBOXED and not self._sandbox_permitted():
            result.outcome = Outcome.SKIPPED
            result.skipped_reason = "sandboxed tasks disabled (HERCULE_EVAL_SANDBOX!=1)"
            result.completed_at = utc_now_iso()
            return self._finish(result, started)
        observed: Any = None
        restore = self._apply_fixtures(task)
        try:
            observed = _run_with_timeout(lambda: self._observed_for(task), task.timeout_s)
        except _TaskTimeout:
            result.outcome = Outcome.TIMEOUT
            result.detail = f"timeout after {task.timeout_s:.0f}s"
            result.completed_at = utc_now_iso()
            return self._finish(result, started)
        except Exception as exc:
            result.outcome = Outcome.ERROR
            result.detail = f"{type(exc).__name__}: {exc}"[:300]
            result.completed_at = utc_now_iso()
            return self._finish(result, started)
        finally:
            try:
                restore()
            except Exception:
                pass
        result.observed = (observed if isinstance(observed, (str, int, float, list, dict))
                           else str(observed))
        result.trace = self._harvest_trace(task, observed)
        if isinstance(observed, dict) and observed.get("latency_ms") is not None:
            try:
                result.timings.execution_ms = float(observed["latency_ms"])
            except (TypeError, ValueError):
                pass
        try:
            result.score = float(self._score_observed(task, observed))
            result.outcome = Outcome.PASSED if result.score >= self._pass_threshold(task) else Outcome.FAILED
            result.detail = ""
        except Exception as exc:
            result.outcome = Outcome.ERROR
            result.score = 0.0
            result.detail = f"scoring error: {type(exc).__name__}: {exc}"[:300]
        result.completed_at = utc_now_iso()
        return self._finish(result, started)

    # --------------------------------------------------
    # Declarative fixtures (UAI Phase M): task.extras entries
    # applied around real-pipeline execution, always restored.
    # --------------------------------------------------
    def _apply_fixtures(self, task: EvalTask):
        """Apply extras fixtures; returns a restore callable (never raises)."""
        undo: List[Callable[[], None]] = []

        def services():
            return getattr(self.adapter, "services", None) or {}

        # register_skill: {"skill": {...}, "validate": bool}
        spec = (task.extras or {}).get("register_skill")
        if isinstance(spec, dict):
            try:
                from cognition.skills import Skill

                manager = (services().get("skills")
                           if isinstance(services(), dict) else None)
                if manager is not None:
                    data = dict(spec.get("skill") or {})
                    skill_id = str(data.get("skill_id", ""))
                    had = manager.get(skill_id) if skill_id else None
                    skill = Skill(**data) if "skill_id" in data else None
                    if skill is not None:
                        manager.register(
                            skill, validate=bool(spec.get("validate", True)))
                        if had is None:
                            undo.append(lambda: manager.unregister(skill_id))
            except Exception:
                pass

        # research_sources: [...] attached to the research ability
        sources = (task.extras or {}).get("research_sources")
        if isinstance(sources, list):
            try:
                abilities = None
                svcs = services()
                if isinstance(svcs, dict):
                    orch = svcs.get("orchestrator")
                    abilities = getattr(orch, "abilities", None)
                research = None
                if abilities is not None:
                    abilities.ensure_defaults()
                    research = abilities.registry.get("research")
                if research is not None and hasattr(research, "attach_source"):
                    class _FixtureSource:
                        def __init__(self, items):
                            self._items = items

                        def execute(self, topic, **kwargs):
                            return {"status": "success", "sources": list(self._items)}

                    research.attach_source(_FixtureSource(sources))
                    undo.append(lambda: research.attach_source(None))
            except Exception:
                pass

        # deny: [capabilities] removed for the duration of the task
        denied = (task.extras or {}).get("deny")
        if isinstance(denied, list) and denied:
            try:
                abilities = None
                svcs = services()
                if isinstance(svcs, dict):
                    orch = svcs.get("orchestrator")
                    abilities = getattr(orch, "abilities", None)
                policy = getattr(abilities, "policy", None)
                if policy is not None:
                    prior = {}
                    for cap in denied:
                        cap = str(cap).upper()
                        try:
                            before = policy.evaluate(cap, {})
                            prior[cap] = bool(before.get("allowed", True))
                        except Exception:
                            prior[cap] = True
                        policy.set_permission(cap, False)
                    undo.append(lambda: [policy.set_permission(c, v)
                                         for c, v in prior.items()])
            except Exception:
                pass

        def restore():
            for fn in reversed(undo):
                try:
                    fn()
                except Exception:
                    pass

        return restore

    @staticmethod
    def _harvest_trace(task: EvalTask, observed: Any) -> Dict[str, Any]:
        """Operational trace from a run_cycle contract (no CoT, ever)."""
        trace: Dict[str, Any] = {}
        if task.autonomy_level is not None:
            trace["autonomy_level"] = task.autonomy_level
        if not isinstance(observed, dict):
            return trace
        for key in ("status", "replans", "retries", "plan_mode"):
            if observed.get(key) is not None:
                trace[key] = observed[key]
        verification = observed.get("verification") or {}
        if isinstance(verification, dict):
            trace["passed_steps"] = int(verification.get("passed_steps", 0) or 0)
            failed = verification.get("failed_steps", [])
            trace["failed_steps"] = len(failed) if isinstance(failed, list) else 0
        result = observed.get("result") or {}
        if isinstance(result, dict):
            completed = result.get("completed", [])
            if isinstance(completed, list):
                trace["completed"] = [str(s)[:40] for s in completed[:12]]
            failed = result.get("failed", [])
            if isinstance(failed, list):
                trace["failed"] = [str((f or {}).get("step_id", f))[:40]
                                   if isinstance(f, dict) else str(f)[:40]
                                   for f in failed[:12]]
        reasoning = observed.get("reasoning") or {}
        if isinstance(reasoning, dict) and reasoning.get("mode"):
            trace["reasoning_mode"] = str(reasoning["mode"])[:24]
        # UAI Phase N1: actual model identification (operational
        # metadata only). Fallback internals are not exposed by the
        # run_cycle contract; when unobservable they stay UNKNOWN.
        if isinstance(reasoning, dict):
            if reasoning.get("model"):
                trace["decision_model"] = str(reasoning["model"])[:120]
            if reasoning.get("provider"):
                trace["decision_provider"] = str(reasoning["provider"])[:48]
            if reasoning.get("reason"):
                trace["decision_reason"] = str(reasoning["reason"])[:200]
        if isinstance(observed.get("evidence"), list):
            trace["evidence_count"] = len(observed["evidence"])
            trace["verification_status"] = str(observed.get("verification_status", ""))[:24]
        if observed.get("skill_id"):
            trace["skill_id"] = str(observed["skill_id"])[:64]
        if isinstance(observed.get("skill"), dict) and observed["skill"].get("skill_id"):
            trace["skill_id"] = str(observed["skill"]["skill_id"])[:64]
            trace["skill_version"] = str(observed["skill"].get("version", ""))[:24]
        if observed.get("error"):
            trace["error"] = str(observed["error"])[:200]
        return trace

    def _finish(self, result: TaskResult, started: float) -> TaskResult:
        result.latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        if callable(self.on_task_done):
            try:
                self.on_task_done(result)
            except Exception:
                pass
        return result

    @staticmethod
    def _pass_threshold(task: EvalTask) -> float:
        return 1.0 if task.scoring_method != ScoringMethod.AGENTIC else 0.7

    @staticmethod
    def _sandbox_permitted() -> bool:
        import os
        return os.environ.get("HERCULE_EVAL_SANDBOX", "") == "1"

    def _run_batch(self, tasks: List[EvalTask], rep: int, parallel: int) -> List[TaskResult]:
        """One repetition pass. ``run_index`` is passed only for repeats
        so subclasses/mocks overriding run_task(task) keep working."""
        use_parallel = (parallel > 1 and not any(
            t.safety_class == SafetyClass.ACTIVE for t in tasks))
        if use_parallel:
            import functools

            with ThreadPoolExecutor(max_workers=parallel) as pool:
                if rep == 1:
                    return list(pool.map(self.run_task, tasks))
                return list(pool.map(
                    functools.partial(self.run_task, run_index=rep), tasks))
        if rep == 1:
            return [self.run_task(t) for t in tasks]
        return [self.run_task(t, run_index=rep) for t in tasks]

    # --------------------------------------------------
    # Suite execution (ACTIVE tasks never run concurrently)
    # --------------------------------------------------
    def run_suite(self, tasks: List[EvalTask], scope: str = "",
                  run_id: str = "") -> SuiteRun:
        tasks = list(tasks or [])
        if self.config.max_tasks and self.config.max_tasks > 0:
            tasks = tasks[:self.config.max_tasks]
        reps = max(1, int(getattr(self.config, "runs", 1) or 1))
        run = SuiteRun(
            run_id=run_id or new_run_id(scope or "suite"),
            scope=scope or (tasks[0].suite if tasks else "empty"),
            version=app_version(), model=self.adapter.default_model(),
            provider=self.adapter.default_provider(),
            started_at=utc_now_iso(), config=self.config.as_dict())
        started = time.perf_counter()
        parallel = max(1, int(self.config.parallel or 1))
        results: List[TaskResult] = []
        for rep in range(1, reps + 1):
            results.extend(self._run_batch(tasks, rep, parallel))
        run.results = results
        run.wall_ms = round((time.perf_counter() - started) * 1000.0, 3)
        run.finished_at = utc_now_iso()
        save_run(run)
        return run
