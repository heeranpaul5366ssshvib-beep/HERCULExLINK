from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Autonomous Execution Loop
Author: Heeran Paul
License: MIT
--------------------------------------------

GOAL -> PLAN -> VALIDATION -> CAPABILITY RESOLUTION -> TOOL/AGENT
MATCHING -> POLICY -> EXECUTION -> OBSERVATION -> VERIFICATION ->
TASK UPDATE -> REPLAN IF REQUIRED -> COMPLETION.

Composes the authoritative Planner, plan validator, ToolMatcher,
AbilityManager/AgentManager, PolicyManager, TaskManager and
verification — it creates no competing flow. Replanning re-enters
the same validated path. Every stage traces via correlation IDs and
persists capability/tool state into the durable task record.
"""

import time
from typing import Any, Callable, Dict, List, Optional

from abilities.tool_matcher import ToolMatchError, ToolMatcher, ToolSelection
from cognition.planner.cognitive import summarize_observation
from cognition.planner.validation import validate_plan
from orchestrator.step_verifier import verify_step


class AutonomousLoop:
    """End-to-end goal execution with validation, fallback and replan."""

    # Bounded autonomy defaults (Phase 4/9): replans, per-step
    # attempts, and wall-clock budget. All configurable per run.
    DEFAULT_MAX_REPLANS = 2
    DEFAULT_MAX_STEP_RETRIES = 1
    DEFAULT_MAX_TOTAL_EXECUTION_TIME = 600.0

    def __init__(
        self,
        planner=None,
        matcher: Optional[ToolMatcher] = None,
        task_manager=None,
        tracer=None,
        max_replans: int = 2,
        max_step_retries: int = 1,
        max_total_execution_time: float = 600.0,
    ):
        self.planner = planner
        self.matcher = matcher
        self.tasks = task_manager
        self.tracer = tracer
        self.max_replans = max_replans
        self.max_step_retries = max_step_retries
        self.max_total_execution_time = max_total_execution_time

    # --------------------------------------------------
    def _trace(self, correlation_id: str, stage: str, data: Dict[str, Any]) -> None:
        if self.tracer is None or not correlation_id:
            return
        try:
            self.tracer.record(correlation_id, stage, data)
        except Exception:
            pass

    def preview(self, goal: str, steps: Optional[List[Any]] = None,
                semantic=None, semantic_proposer=None) -> Dict[str, Any]:
        """Structured execution preview: no chain-of-thought, no execution."""
        plan = self.planner.create_capable_plan(goal, steps or [goal],
                                                semantic=semantic, proposer=semantic_proposer)
        validation = self._validate(plan, goal)
        resolutions = []
        for step in plan:
            try:
                selection = self.matcher.match(step) if self.matcher else None
                resolutions.append({"step_id": step["step_id"], "ok": True,
                                    "tool": selection.selected.as_dict() if selection else None,
                                    "coverage": selection.coverage if selection else "UNKNOWN"})
            except ToolMatchError as exc:
                resolutions.append({"step_id": step["step_id"], "ok": False,
                                    "error": str(exc), "code": exc.code})
        return {"goal": goal, "plan": plan, "validation": validation, "resolutions": resolutions}

    def _validate(self, plan: List[Dict[str, Any]], correlation_id: str = "") -> Dict[str, Any]:
        matcher = self.matcher
        report = validate_plan(
            plan,
            capability_registry=getattr(matcher, "registry", None),
            policy_manager=getattr(matcher, "policy", None),
            environment=getattr(matcher, "environment", "default"),
            ability_manager=getattr(matcher, "abilities", None),
            agent_manager=getattr(matcher, "agents", None),
        )
        self._trace(correlation_id, "plan_validation",
                    {"valid": report["valid"], "problems": report["problems"], "metrics": report["metrics"]})
        return report

    def _persist_step(self, task_id: str, step: Dict[str, Any], selection=None,
                      verification: Optional[Dict[str, Any]] = None, failure: str = "") -> None:
        if self.tasks is None or not task_id:
            return
        try:
            import hashlib
            from datetime import datetime, timezone
            task = self.tasks.get(task_id)
            meta = task.setdefault("metadata", {})
            states = meta.setdefault("capability_states", {})
            fingerprint = hashlib.sha256(str(step.get("description", "")).encode("utf-8")).hexdigest()[:12]
            states[step.get("step_id", "")] = {
                "required_capabilities": step.get("required_capabilities", []),
                "selected_tool": selection.selected.as_dict() if selection else None,
                "status": step.get("status", "pending"),
                "verification": verification,
                "retries": step.get("_attempts", 0),
                "failure": failure,
                "effect": step.get("effect", "EFFECTFUL"),
                "resume_policy": step.get("resume_policy", "default"),
                "compensation": step.get("compensation"),
                "environment": getattr(self.matcher, "environment", "default") if self.matcher else "default",
                "input_fingerprint": fingerprint,
                "checkpointed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.tasks.record_checkpoint(task_id, {"step": step.get("step_id"), "state": states[step.get("step_id", "")]},
                                         checkpoint_type="capability")
        except Exception:
            pass

    def _completed_step_ids(self, task_id: str) -> set:
        """Steps already verified-complete (resume support, §12)."""
        if not self.tasks or not task_id:
            return set()
        try:
            states = self.tasks.get(task_id).get("metadata", {}).get("capability_states", {})
            return {sid for sid, s in states.items() if (s or {}).get("status") == "completed"}
        except Exception:
            return set()

    def _task_cancelled(self, task_id: str) -> bool:
        if not self.tasks or not task_id:
            return False
        try:
            return str(self.tasks.status(task_id)).upper() == "CANCELLED"
        except Exception:
            return False

    # --------------------------------------------------
    def run(self, goal: str, steps: Optional[List[Any]] = None, task_id: str = "",
            correlation_id: str = "", payload_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
            semantic=None, semantic_proposer=None,
            preferred: Optional[Dict[str, str]] = None,
            time_budget_s: Optional[float] = None,
            chain: bool = False,
            replan_proposer=None) -> Dict[str, Any]:
        """Execute a goal end to end. Returns a completion report.

        ``preferred`` maps CAPABILITY -> ability name from past successful
        experience; it only reorders healthy, policy-approved candidates
        (revalidation always applies, never overrides security).
        ``time_budget_s`` caps wall-clock execution (default
        ``max_total_execution_time``). Dependent steps wait for verified
        prerequisites; nothing executes on assumed success.
        ``replan_proposer`` is an optional adaptive hook
        fn(failed_step, observation_summary) -> [step descriptions];
        its suggestions re-enter deterministic inference + validation,
        and any failure falls back to the conservative replan.
        Ready steps run in dependency-safe order (independent branches
        continue past unrelated failures); deadlocks fail honestly.
        """
        started = time.perf_counter()
        budget = self.max_total_execution_time if time_budget_s is None else float(time_budget_s)
        plan = self.planner.create_capable_plan(goal, steps or [goal],
                                                semantic=semantic, proposer=semantic_proposer,
                                                chain=chain)
        # v1.1: REFERENCE RESOLUTION -> PLAN VALIDATION -> CAPABILITY
        # RESOLUTION -> EXECUTION. Resolved wording re-enters validation
        # unchanged; reference failures abort before any tool matching.
        try:
            from cognition.planner.references import resolve_plan_references
            plan, _ref_report = resolve_plan_references(plan, context=None)
            if _ref_report.get("resolutions"):
                self._trace(correlation_id, "reference_resolution",
                            {"resolutions": _ref_report.get("resolutions")})
        except Exception as exc:
            try:
                from cognition.planner.references import ReferenceResolutionError
                if isinstance(exc, ReferenceResolutionError):
                    self._trace(correlation_id, "reference_resolution",
                                {"ok": False, **exc.as_dict()})
                    return {"status": "failed",
                            "completed": [], "failed": [
                                {"step_id": exc.step_id or "",
                                 "reason": exc.code,
                                 "detail": exc.detail,
                                 "candidates": list(exc.candidates)}],
                            "replans": 0,
                            "error": f"{exc.code}: {exc.detail} candidates={exc.candidates}",
                            "correlation_id": correlation_id}
            except Exception:
                pass
            # Non-reference errors must never break the frozen path: fall
            # through to validation with the original plan.
            pass
        replans = 0
        completed: List[str] = []
        failed: List[Dict[str, Any]] = []
        step_attempts: Dict[str, int] = {}
        already_done = self._completed_step_ids(task_id)
        done_ids = set(already_done)
        pending = [s for s in plan if s.get("step_id") not in already_done]
        skipped = sorted(already_done & {s.get("step_id", "") for s in plan})
        validation = self._validate(plan, correlation_id)
        cancelled = False
        known_ids = {str(s.get("step_id", "")) for s in plan}
        self._trace(correlation_id, "dependency_graph",
                    {"edges": {str(s.get("step_id", "")): list(s.get("dependencies", []) or [])
                               for s in plan}})
        failed_ids: set = set()
        deferred = 0

        def _elapsed() -> float:
            return time.perf_counter() - started

        while pending:
            if _elapsed() > budget:
                failed.append({"reason": "time budget exhausted",
                               "detail": f"exceeded {budget:.0f}s with {len(pending)} steps pending"})
                self._trace(correlation_id, "replan",
                            {"failed_step": "", "errors": ["time budget exhausted"], "recovery": "none"})
                break
            if self._task_cancelled(task_id):
                failed.append({"reason": "cancelled", "detail": "task cancelled; remaining steps not executed"})
                cancelled = True
                break
            if not validation["valid"]:
                failed.append({"reason": "plan invalid", "problems": validation["problems"]})
                break
            step = pending.pop(0)
            step_id = step.get("step_id", "")
            # Dependency gate (Stage 8): a step runs only after every
            # prerequisite is verified-complete. Doomed prerequisites
            # (failed/unknown) block honestly; still-pending ones defer
            # so independent branches continue. Rotation is capped, so
            # deadlocks fail instead of looping forever.
            unmet = [str(d) for d in (step.get("dependencies", []) or []) if d not in done_ids]
            if unmet:
                doomed = [d for d in unmet if d in failed_ids or d not in known_ids]
                if not doomed:
                    pending.append(step)
                    deferred += 1
                    if deferred > len(pending):
                        for leftover in pending:
                            lid = leftover.get("step_id", "")
                            failed.append({"step_id": lid, "reason": "blocked",
                                           "detail": "dependency deadlock: no ready step"})
                            failed_ids.add(lid)
                            self._trace(correlation_id, "step",
                                        {"step_id": lid, "status": "blocked",
                                         "detail": "dependency deadlock"})
                            self._persist_step(task_id, leftover,
                                               failure="dependency deadlock")
                        pending.clear()
                        break
                    continue
                failed.append({"step_id": step_id, "reason": "blocked",
                               "detail": f"unverified prerequisites: {unmet}"})
                failed_ids.add(step_id)
                self._trace(correlation_id, "step",
                            {"step_id": step_id, "status": "blocked", "unmet_dependencies": unmet})
                self._persist_step(task_id, step, failure=f"blocked by unverified prerequisites: {unmet}")
                continue
            deferred = 0
            step_attempts[step_id] = step_attempts.get(step_id, 0) + 1
            if step_attempts[step_id] > self.max_step_retries + 1:
                failed.append({"step_id": step_id, "reason": "step retry budget exhausted",
                               "detail": f"{step_attempts[step_id] - 1} visits, no verified result"})
                self._trace(correlation_id, "step",
                            {"step_id": step_id, "status": "retry-exhausted",
                             "attempts": step_attempts[step_id] - 1})
                self._persist_step(task_id, step, failure="step retry budget exhausted")
                continue
            # MAX_STEP_RETRIES surfaces as the step's retry_policy so the
            # executor (not just this loop) enforces per-step attempt caps.
            policy = step.get("retry_policy")
            if not isinstance(policy, dict) or "max_retries" not in policy:
                step["retry_policy"] = dict(policy or {})
                step["retry_policy"]["max_retries"] = self.max_step_retries
                step["retry_policy"].setdefault("retry_destructive", False)
            self._trace(correlation_id, "step",
                        {"step_id": step_id, "description": str(step.get("description", ""))[:160],
                         "attempt": step_attempts[step_id],
                         "dependencies": list(step.get("dependencies", []) or [])})
            try:
                selection = self.matcher.match(step, preferred=preferred)
            except ToolMatchError as exc:
                self._trace(correlation_id, "capability_resolution",
                            {"step_id": step_id, "ok": False, "error": str(exc), "code": exc.code})
                failed.append({"step_id": step_id, "reason": str(exc), "code": exc.code})
                failed_ids.add(step_id)
                self._persist_step(task_id, step, failure=str(exc))
                continue
            self._trace(correlation_id, "capability_resolution",
                        {"step_id": step_id, "ok": True, "tool": selection.selected.as_dict(),
                         "rejected": selection.rejected, "coverage": selection.coverage})
            step["status"] = "running"
            self._persist_step(task_id, step, selection, None, "")
            self._trace(correlation_id, "ability",
                        {"step_id": step_id, "ability": selection.selected.name,
                         "kind": selection.selected.kind,
                         "covers": list(selection.selected.covers)})
            self._trace(correlation_id, "permission",
                        {"step_id": step_id, "ability": selection.selected.name,
                         "allowed": (selection.selected.permission or {}).get("allowed", True),
                         "risk": (selection.selected.permission or {}).get("risk", "")})
            payload = payload_fn(step) if payload_fn else {}
            outcome = self.matcher.execute_with_fallback(selection, step, payload)
            self._trace(correlation_id, "execution",
                        {"step_id": step_id, "status": outcome["status"], "attempts": outcome["attempts"],
                         "executor": (outcome["executor"] or {}).get("name") if outcome["executor"] else None})
            if outcome["status"] == "success":
                observed = outcome.get("result")
                self._trace(correlation_id, "observation",
                            {"step_id": step_id,
                             "summary": str(observed)[:200] if not isinstance(observed, dict) else
                             str({k: (str(v)[:120]) for k, v in list(observed.items())[:6]})[:200]})
            if outcome["status"] != "success":
                verification = {"passed": False, "detail": "; ".join(outcome["errors"])}
                self._persist_step(task_id, step, selection, verification, "; ".join(outcome["errors"]))
                self._trace(correlation_id, "verification", {"step_id": step_id, **verification})
                if replans < self.max_replans:
                    replans += 1
                    replan_steps = self._replan(goal, step, outcome, correlation_id, task_id,
                                                replan_proposer=replan_proposer,
                                                observation=summarize_observation(outcome))
                    replan = self.planner.create_capable_plan(f"{goal} (replan {replans})", replan_steps,
                                                                semantic=semantic, proposer=semantic_proposer)
                    self._tag_replan_ids(replan, replans)
                    self._cap_replan_retries(replan)
                    validation = self._validate(replan, correlation_id)
                    known_ids.update(s.get("step_id", "") for s in replan)
                    pending = list(replan) + pending
                    continue
                failed.append({"step_id": step_id, "reason": "execution failed", "errors": outcome["errors"]})
                failed_ids.add(step_id)
                continue
            actual = outcome.get("executor") or {}
            if actual.get("name") and actual.get("name") != selection.selected.name:
                # Fallback won: persist the tool that actually executed,
                # not the first-ranked candidate, so lessons stay honest.
                for cand in selection.candidates:
                    if cand.name == actual.get("name") and cand.kind == actual.get("kind"):
                        selection = ToolSelection(
                            selection.step_id, cand, selection.candidates,
                            selection.rejected + [{
                                "kind": selection.selected.kind,
                                "name": selection.selected.name,
                                "reason": "fallback: first candidate failed honestly"}],
                            selection.coverage)
                        break
            verification = verify_step(step, outcome)
            self._trace(correlation_id, "verification", {"step_id": step_id, **verification})
            step["_attempts"] = outcome["attempts"]
            if verification.get("passed"):
                step["status"] = "completed"
                completed.append(step_id)
                done_ids.add(step_id)
            else:
                step["status"] = "failed-verification"
                if replans < self.max_replans:
                    replans += 1
                    replan_steps = self._replan(goal, step, {"errors": [verification.get("detail", "")]}, correlation_id, task_id,
                                                replan_proposer=replan_proposer,
                                                observation=summarize_observation(outcome))
                    replan = self.planner.create_capable_plan(f"{goal} (replan {replans})", replan_steps,
                                                                semantic=semantic, proposer=semantic_proposer)
                    self._tag_replan_ids(replan, replans)
                    self._cap_replan_retries(replan)
                    validation = self._validate(replan, correlation_id)
                    known_ids.update(s.get("step_id", "") for s in replan)
                    pending = list(replan) + pending
                    self._persist_step(task_id, step, selection, verification, verification.get("detail", ""))
                    continue
                failed.append({"step_id": step_id, "reason": "verification failed", "detail": verification.get("detail")})
                failed_ids.add(step_id)
            self._persist_step(task_id, step, selection, verification)

        total_ms = (time.perf_counter() - started) * 1000.0
        if cancelled:
            status = "cancelled"
        else:
            status = "completed" if not failed and completed else ("partial" if completed else "failed")
        return {"goal": goal, "status": status, "completed": completed, "failed": failed,
                "replans": replans, "skipped": skipped, "latency_ms": round(total_ms, 3)}

    @staticmethod
    def _tag_replan_ids(replan: List[Dict[str, Any]], replans: int) -> None:
        """Unique replan step ids so resume-skip never confuses attempts."""
        for i, step in enumerate(replan):
            step["step_id"] = f"step-r{replans}-{i + 1}"

    def _cap_replan_retries(self, replan: List[Dict[str, Any]]) -> None:
        """Bound replan steps by the loop's per-step retry cap (stricter wins).

        The planner stamps its own default retry policy; the loop-level
        MAX_STEP_RETRIES remains authoritative for safe autonomy.
        """
        for step in replan:
            policy = step.get("retry_policy")
            if not isinstance(policy, dict):
                step["retry_policy"] = {"max_retries": self.max_step_retries,
                                        "retry_destructive": False}
                continue
            try:
                policy["max_retries"] = min(int(policy.get("max_retries", self.max_step_retries)),
                                            int(self.max_step_retries))
            except (TypeError, ValueError):
                policy["max_retries"] = self.max_step_retries

    def _replan(self, goal: str, failed_step: Dict[str, Any], outcome: Dict[str, Any],
                correlation_id: str, task_id: str = "",
                replan_proposer=None, observation: str = "") -> List[str]:
        """Bounded recovery: classify, consult experience, decide, propose.

        Phase 5 (Decision Intelligence): recovery CANDIDATES are generated
        deterministically (retry wording, alternative-tool hint) plus an
        optional adaptive proposer suggestion; the DecisionEngine ranks the
        validated candidates and the highest-scoring recovery wording is
        emitted. Never invents tools: the replan re-enters match/policy/
        verification exactly like any other steps.
        """
        from evaluation.failures import classify_failure

        errors = outcome.get("errors", []) if isinstance(outcome, dict) else [str(outcome)]
        classification = classify_failure("; ".join(str(e) for e in errors),
                                          task_id=task_id, correlation_id=correlation_id)
        adaptive = False
        descriptions: List[str] = []
        if callable(replan_proposer):
            try:
                from cognition.planner.cognitive import summarize_observation
                candidate = replan_proposer(failed_step, observation or summarize_observation(outcome))
                if isinstance(candidate, list):
                    descriptions = [str(d).strip() for d in candidate
                                    if str(d or "").strip()][:2]
                    adaptive = bool(descriptions)
            except Exception as exc:
                self._trace(correlation_id, "replan",
                            {"failed_step": failed_step.get("step_id"),
                             "adaptive_proposal": "rejected", "error": str(exc)[:160]})
        self._trace(correlation_id, "replan",
                    {"failed_step": failed_step.get("step_id"), "errors": errors,
                     "failure_category": classification.category.value,
                     "failure_code": classification.code,
                     "retryable": classification.retryable,
                     "experience_guided": True, "adaptive": adaptive})
        # Phase 5: deterministic recovery candidates + DecisionEngine ranking.
        description = str(failed_step.get("description", ""))
        try:
            selected_desc = self._decide_recovery(goal, failed_step, descriptions,
                                                  classification, correlation_id)
        except Exception:
            selected_desc = None
        if selected_desc:
            return [selected_desc]
        if adaptive:
            return descriptions
        # Conservative replan: retry the failed objective with an explicit
        # alternative-tool hint encoded as a step variant.
        return [f"Alternative approach for: {description}"]

    def _decide_recovery(self, goal: str, failed_step: Dict[str, Any],
                         adaptive: List[str], classification, correlation_id: str) -> str:
        """Rank recovery candidates with the Phase-5 DecisionEngine (§13).

        Deterministic candidates (original retry, explicit alternative-tool
        variant) are always generated; adaptive proposer wordings join them
        when present. Everything re-enters the normal plan validation
        downstream; this only chooses the wording, never bypasses policy.
        """
        from cognition.decision.strategy import CandidateStrategy, decide_strategies

        description = str(failed_step.get("description", ""))
        caps = [str(c).upper() for c in (failed_step.get("required_capabilities") or [])]
        candidates = [CandidateStrategy(
            strategy_id="recovery-retry",
            goal=goal,
            steps=[{"step_id": "recovery-1", "goal": description,
                    "required_capabilities": caps or ["FILE_READ"],
                    "risk": str(failed_step.get("risk", "LOW")).upper()}],
            required_capabilities=caps,
            risk=str(failed_step.get("risk", "LOW")).upper(),
            verification_difficulty="STANDARD",
            source="recovery-retry",
        ), CandidateStrategy(
            strategy_id="recovery-alternative",
            goal=goal,
            steps=[{"step_id": "recovery-1",
                    "goal": f"Alternative approach for: {description}",
                    "required_capabilities": caps or ["FILE_READ"],
                    "risk": str(failed_step.get("risk", "LOW")).upper()}],
            required_capabilities=caps,
            risk=str(failed_step.get("risk", "LOW")).upper(),
            verification_difficulty="STANDARD",
            source="recovery-alternative",
        )]
        for i, wording in enumerate(adaptive[:2]):
            candidates.append(CandidateStrategy(
                strategy_id=f"recovery-adaptive-{i+1}",
                goal=goal,
                steps=[{"step_id": "recovery-1", "goal": wording,
                        "required_capabilities": caps or ["FILE_READ"],
                        "risk": str(failed_step.get("risk", "LOW")).upper()}],
                required_capabilities=caps,
                risk=str(failed_step.get("risk", "LOW")).upper(),
                verification_difficulty="STANDARD",
                source="recovery-adaptive",
            ))
        # Retry on the exact same wording is preferred when the failure is
        # retryable (transient); otherwise the alternative wording wins the
        # tie-break. Experience/fit inputs stay advisory.
        weights = {"expected_success": 1.0}  # keep scoring stable & small
        rec = decide_strategies(goal, candidates,
                                experience_stats={},
                                available_capabilities=caps or None,
                                weights=weights)
        try:
            classification.retryable
            retryable = bool(getattr(classification, "retryable", False))
        except Exception:
            retryable = False
        if retryable:
            # Prefer the plain retry candidate when the failure class is
            # retryable and its decision score is not strictly worse.
            retry_score = rec.scores.get("recovery-retry", float("-inf"))
            best_score = max(rec.scores.values(), default=float("-inf"))
            if retry_score >= best_score - 0.5:
                return description
        self._trace(correlation_id, "recovery_decision",
                    {"candidates": [c.strategy_id for c in candidates],
                     "scores": {k: round(v, 3) for k, v in rec.scores.items()},
                     "selected": rec.selected.strategy_id if rec.selected else None,
                     "reason": rec.selection_reason[:160]})
        selected = rec.selected
        if selected is None:
            return ""
        return str(selected.steps[0].get("goal", "")) if selected.steps else ""
