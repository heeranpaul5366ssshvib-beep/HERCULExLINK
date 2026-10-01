from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Computer Controller (v1.2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Bounded OBSERVE -> PLAN -> APPROVE -> ACT -> OBSERVE -> VERIFY loop
for multi-step computer interaction. The controller never invents
actions: callers supply structured proposals (or single actions via
``run_action``); policy gates every step; approval blocks HIGH-risk
execution until a human decides; verification confirms each step.

Bounds (all enforced): max actions, max retries, max replans, max
runtime. Exceeding any bound aborts honestly — infinite loops are
impossible. Thread-safe; ``cancel()`` stops the loop promptly. The UI
thread never blocks: run in a worker and poll ``snapshot()``.
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from computer.actions import (
    ActionError,
    ComputerAction,
    parse_action,
    validate_coordinates,
)
from computer.adapters.desktop import ComputerUnavailable, DesktopAdapter
from computer.config import ComputerConfig, load_computer_config
from computer.policy import (
    ApprovalStore,
    PolicyViolation,
    check_application,
    check_freshness,
    decide,
)
from computer.verifier import verify


class ComputerController:
    """Owns adapter, policy, approvals, bounds, and HUD state."""

    STATES = ("IDLE", "OBSERVING", "ACTION_PROPOSED", "APPROVAL_REQUIRED",
              "EXECUTING", "VERIFYING", "COMPLETED", "FAILED", "CANCELLED")

    def __init__(self, config: Optional[ComputerConfig] = None,
                 adapter: Any = None,
                 approvals: Optional[ApprovalStore] = None,
                 on_approval: Optional[Callable[[Dict[str, Any]], bool]] = None):
        self.config = config or load_computer_config()
        self.adapter = adapter or DesktopAdapter(
            timeout_s=self.config.action_timeout_s)
        self.approvals = approvals or ApprovalStore(
            timeout_s=self.config.approval_timeout_s)
        # on_approval(request_dict) -> True/False; None = no interactive
        # approver: HIGH-risk actions stay blocked (never auto-approved).
        self.on_approval = on_approval
        self._lock = threading.RLock()
        self._state = "IDLE"
        self._cancel = threading.Event()
        self._current: Optional[Dict[str, Any]] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._last_observation: Optional[Dict[str, Any]] = None
        self._history: List[Dict[str, Any]] = []

    # --------------------------------------------------
    # State / cancellation / HUD snapshot
    # --------------------------------------------------
    def _set_state(self, state: str) -> None:
        with self._lock:
            self._state = state

    def cancel(self) -> Dict[str, Any]:
        self._cancel.set()
        try:
            self.adapter.stop()  # type: ignore[attr-defined]
        except Exception:
            pass
        self._set_state("CANCELLED")
        return {"status": "cancelled"}

    def reset(self) -> None:
        self._cancel.clear()
        with self._lock:
            self._history = []
            self._last_result = None
            self._current = None
        self._set_state("IDLE")

    def snapshot(self) -> Dict[str, Any]:
        """Real HUD state (never fabricated actions or verifications)."""
        with self._lock:
            current = dict(self._current or {})
            result = dict(self._last_result or {})
            pending = []
            try:
                pending = [{"request_id": r.request_id, "action": r.action,
                            "risk": r.risk, "app": r.app}
                           for r in self.approvals.pending()]
            except Exception:
                pending = []
            return {
                "enabled": bool(self.config.enabled),
                "state": self._state,
                "current_application": str(current.get("app", "") or ""),
                "proposed_action": str(current.get("action", "") or ""),
                "risk": str(current.get("risk", "") or ""),
                "approval": str(current.get("approval", "") or ""),
                "executing": self._state == "EXECUTING",
                "verifying": self._state == "VERIFYING",
                "verified": result.get("verification", {}).get("verified", False)
                if isinstance(result.get("verification"), dict) else False,
                "pending_approvals": pending,
                "history": list(self._history)[-10:],
                "last_error": str(result.get("error", "") or "")[:200],
            }

    # --------------------------------------------------
    # Observation (explicit only; reused when fresh)
    # --------------------------------------------------
    def observe(self, force: bool = False) -> Dict[str, Any]:
        """Capture a fresh observation (screenshot + clock)."""
        with self._lock:
            if (not force and self._last_observation is not None
                    and time.time() - float(self._last_observation.get("at", 0))
                    <= self.config.observation_max_age_s):
                return dict(self._last_observation)
        self._set_state("OBSERVING")
        try:
            png, width, height = self.adapter.screenshot()
        except Exception as exc:
            raise ComputerUnavailable(f"observation failed: {exc}")
        observation = {"at": time.time(), "width": width, "height": height,
                       "bytes": len(png), "png": png}
        with self._lock:
            self._last_observation = observation
        return dict(observation)

    # --------------------------------------------------
    # Single action: PROPOSE -> POLICY -> APPROVE -> ACT -> VERIFY
    # --------------------------------------------------
    def run_action(self, proposal: Dict[str, Any],
                   expect: Optional[Dict[str, Any]] = None,
                   approval_id: str = "",
                   screen: Optional[Any] = None,
                   wait_for_approval: bool = False) -> Dict[str, Any]:
        """Execute one structured proposal through the full gate chain.

        ``wait_for_approval`` (interactive controller use only) blocks
        boundedly for a human decision; the ability pipeline leaves it
        False so HIGH-risk steps return APPROVAL_REQUIRED immediately
        instead of stalling autonomous execution.
        """
        if not self.config.enabled:
            return {"status": "rejected",
                    "error": "computer control is disabled (opt-in)"}
        if self._cancel.is_set():
            self._set_state("CANCELLED")
            return {"status": "cancelled"}
        try:
            action = parse_action(proposal)
        except ActionError as exc:
            return {"status": "failed", "error": str(exc)[:300],
                    "code": exc.code}
        if screen is None:
            try:
                width, height = self.adapter.screen_size()
                screen = (width, height)
            except Exception as exc:
                return {"status": "failed",
                        "error": f"screen unavailable: {exc}"[:300]}
        try:
            validate_coordinates(action, (int(screen[0]), int(screen[1])))
        except ActionError as exc:
            return {"status": "failed", "error": str(exc)[:300],
                    "code": exc.code}
        with self._lock:
            self._current = {**action.as_dict(), "approval": "checking"}
        self._set_state("ACTION_PROPOSED")
        # Policy gate (application + freshness + approval).
        try:
            check_application(action, self.config.allowed_apps)
            check_freshness(action, self.config.observation_max_age_s)
            receipt = decide(action, self.config.allowed_apps,
                             self.config.observation_max_age_s,
                             self.approvals, approval_id=approval_id)
        except PolicyViolation as exc:
            with self._lock:
                self._current = {**action.as_dict(),
                                 "approval": "required"
                                 if exc.code == "APPROVAL_REQUIRED" else "denied"}
                self._last_result = {"status": "blocked", "error": str(exc)[:300],
                                     "code": exc.code, "action": action.as_dict()}
            if exc.code == "APPROVAL_REQUIRED":
                self._set_state("APPROVAL_REQUIRED")
                if wait_for_approval or self.on_approval is not None:
                    return self._await_approval(action, expect, screen)
                result = {"status": "blocked",
                          "error": str(exc)[:300], "code": exc.code,
                          "action": action.as_dict(),
                          "request_id": self._latest_request_id()}
                return self._finish(result)
            self._set_state("FAILED")
            return dict(self._last_result)
        with self._lock:
            self._current = {**action.as_dict(),
                             "approval": str(receipt.get("approval", ""))}
        # Act (bounded by the adapter timeout; adapter errors are honest
        # failures, never escapes).
        self._set_state("EXECUTING")
        try:
            dispatch = self._dispatch(action)
        except ActionError as exc:
            result = {"status": "failed", "error": str(exc)[:300],
                      "code": exc.code, "action": action.as_dict()}
            return self._finish(result)
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)[:300],
                      "action": action.as_dict()}
            return self._finish(result)
        # Verify (never claim without evidence).
        self._set_state("VERIFYING")
        verification = verify(action, dispatch, self.adapter,
                              expect=expect or {})
        result = {"status": "completed" if verification.get("verified") else "failed",
                  "action": action.as_dict(), "dispatch": dispatch,
                  "verification": verification}
        if not verification.get("verified"):
            result["error"] = str(verification.get("detail", "unverified"))[:300]
        return self._finish(result)

    def _latest_request_id(self) -> str:
        try:
            pending = self.approvals.pending()
            return pending[-1].request_id if pending else ""
        except Exception:
            return ""

    def _await_approval(self, action: ComputerAction,
                        expect: Optional[Dict[str, Any]],
                        screen: Any) -> Dict[str, Any]:
        """Block (bounded) for a human decision; never auto-approve."""
        pending = self.approvals.pending()
        request_id = pending[-1].request_id if pending else ""
        if self.on_approval is not None and request_id:
            try:
                approved = self.on_approval({"request_id": request_id,
                                             "action": action.as_dict(),
                                             "risk": action.risk,
                                             "app": action.app})
            except Exception:
                approved = False
            try:
                if approved:
                    self.approvals.approve(request_id)
                else:
                    self.approvals.reject(request_id)
            except PolicyViolation:
                pass
            return self.run_action({**action.as_dict(),
                                    "observed_at": action.observed_at},
                                   expect=expect, approval_id=request_id,
                                   screen=screen)
        deadline = time.perf_counter() + self.config.approval_timeout_s
        while time.perf_counter() < deadline:
            if self._cancel.is_set():
                self._set_state("CANCELLED")
                return {"status": "cancelled"}
            req = self.approvals.status(request_id) if request_id else None
            state = req.state if req else ""
            if state == "APPROVED":
                return self.run_action({**action.as_dict(),
                                        "observed_at": action.observed_at},
                                       expect=expect, approval_id=request_id,
                                       screen=screen)
            if state in ("REJECTED", "EXPIRED"):
                self._set_state("FAILED")
                result = {"status": "blocked",
                          "error": f"approval {state.lower()} for {action.action}",
                          "code": "APPROVAL_DENIED",
                          "action": action.as_dict()}
                return self._finish(result)
            time.sleep(0.25)
        self._set_state("FAILED")
        return self._finish({"status": "blocked",
                             "error": "approval timed out; no execution occurred",
                             "code": "APPROVAL_REQUIRED",
                             "action": action.as_dict()})

    def _dispatch(self, action: ComputerAction) -> Dict[str, Any]:
        name = action.action
        adapter = self.adapter
        if name == "screenshot":
            png, width, height = adapter.screenshot()
            with self._lock:
                self._last_observation = {"at": time.time(), "width": width,
                                          "height": height, "bytes": len(png),
                                          "png": png}
            return {"screenshot": True, "bytes": len(png),
                    "png_bytes": [len(png)]}
        if name == "move":
            x, y = action.coordinates or (0, 0)
            return adapter.move(x, y)
        if name in ("click", "double_click", "right_click"):
            x, y = action.coordinates or (0, 0)
            kind = "right" if name == "right_click" else "left"
            return adapter.click(x, y, kind=kind,
                                 double=(name == "double_click"))
        if name == "scroll":
            x = y = None
            if action.coordinates:
                x, y = action.coordinates
            return adapter.scroll(action.amount, x, y)
        if name == "type":
            return adapter.type_text(action.text,
                                     timeout_s=self.config.action_timeout_s)
        if name == "press_key":
            return adapter.press_key(action.key)
        if name == "hotkey":
            return adapter.hotkey(action.hotkey)
        if name == "wait":
            time.sleep(min(30.0, max(0.5, action.seconds)))
            return {"waited": True, "seconds": action.seconds}
        if name == "open_app":
            from computer.policy import APP_LAUNCH_COMMANDS

            command = APP_LAUNCH_COMMANDS.get(action.app, [f"{action.app}.exe"])
            return adapter.open_app(command,
                                    timeout_s=self.config.action_timeout_s)
        raise ActionError("INVALID_ACTION", f"no executor for {name!r}")

    def _finish(self, result: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._last_result = dict(result)
            entry = {"action": (result.get("action") or {}).get("action", ""),
                     "status": result.get("status", ""),
                     "verified": bool((result.get("verification") or {})
                                      .get("verified", False))}
            self._history.append(entry)
        self._set_state("COMPLETED" if result.get("status") == "completed"
                        else "FAILED" if result.get("status") == "failed"
                        else str(self._state))
        return dict(result)

    # --------------------------------------------------
    # Bounded multi-step sequence
    # --------------------------------------------------
    def run_sequence(self, proposals: List[Dict[str, Any]],
                     expects: Optional[List[Dict[str, Any]]] = None
                     ) -> Dict[str, Any]:
        """OBSERVE -> (PLAN supplied) -> APPROVE -> ACT -> VERIFY per step.

        Bounded by max_actions / max_retries / max_replans / max_runtime_s.
        """
        if not self.config.enabled:
            return {"status": "rejected",
                    "error": "computer control is disabled (opt-in)"}
        self.reset()
        started = time.perf_counter()
        steps = list(proposals or [])[:self.config.max_actions + 1]
        if len(proposals or []) > self.config.max_actions:
            return {"status": "failed", "error": f"too many actions "
                    f"(max {self.config.max_actions})", "code": "LIMIT_ACTIONS"}
        completed, failed, replans = [], [], 0
        step_details: List[Dict[str, Any]] = []
        for index, proposal in enumerate(steps):
            if self._cancel.is_set():
                return self._sequence_result("cancelled", completed, failed,
                                             replans, started,
                                             step_details=step_details)
            if time.perf_counter() - started > self.config.max_runtime_s:
                return self._sequence_result("failed", completed, failed,
                                             replans, started,
                                             error="max runtime exceeded",
                                             code="LIMIT_RUNTIME")
            expect = (expects or [])[index] if expects and index < len(expects) else {}
            # Fresh observation per sensitive step (only when needed).
            try:
                probe = parse_action(proposal)
            except ActionError as exc:
                failed.append({"step": index, "error": str(exc)[:200]})
                continue
            if probe.risk != "LOW" and probe.action not in ("wait",):
                try:
                    self.observe()
                    proposal = {**proposal, "observed_at": time.time()}
                except ComputerUnavailable as exc:
                    failed.append({"step": index, "error": str(exc)[:200]})
                    continue
            attempts = 0
            while True:
                result = self.run_action(proposal, expect=expect)
                if result.get("status") == "completed":
                    completed.append(index)
                    step_details.append({"step": index,
                                         "action": result.get("action", {}),
                                         "verified": bool((result.get("verification") or {})
                                                           .get("verified", False))})
                    break
                if result.get("status") in ("blocked", "cancelled", "rejected"):
                    failed.append({"step": index, **result})
                    if result.get("status") != "failed":
                        return self._sequence_result(result["status"], completed,
                                                     failed, replans, started,
                                                     step_details=step_details)
                    break
                attempts += 1
                if attempts > self.config.max_retries:
                    if replans >= self.config.max_replans:
                        failed.append({"step": index, **result})
                        step_details.append({"step": index,
                                             "action": result.get("action", {}),
                                             "verified": False})
                        break
                    replans += 1
                    try:
                        self.observe(force=True)
                        proposal = {**proposal, "observed_at": time.time()}
                    except ComputerUnavailable:
                        pass
                    attempts = 0
                    continue
                time.sleep(0.3)
        status = "completed" if failed == [] else ("partial" if completed else "failed")
        return self._sequence_result(status, completed, failed, replans, started,
                                     step_details=step_details)

    def _sequence_result(self, status: str, completed: List[int],
                         failed: List[Dict[str, Any]], replans: int,
                         started: float, error: str = "",
                         code: str = "",
                         step_details: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": status, "completed": completed, "failed": failed,
            "replans": replans, "steps": list(step_details or []),
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 2)}
        if error:
            result["error"] = error
        if code:
            result["code"] = code
        with self._lock:
            self._last_result = dict(result)
        self._set_state("COMPLETED" if status == "completed"
                        else "CANCELLED" if status == "cancelled" else "FAILED")
        return result


_SHARED_CONTROLLER: Optional["ComputerController"] = None
_SHARED_LOCK = threading.Lock()


def shared_controller() -> "ComputerController":
    """Process-wide controller so ability, UI, and HUD share approvals."""
    global _SHARED_CONTROLLER
    with _SHARED_LOCK:
        if _SHARED_CONTROLLER is None:
            _SHARED_CONTROLLER = ComputerController()
        return _SHARED_CONTROLLER
