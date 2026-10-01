from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Computer-Use Policy (v1.2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Deterministic policy for computer actions. Decides, per action:

* is the target application allowed or denied?
* is the grounding observation fresh enough?
* is explicit human approval required / granted / denied?

The model proposes; this policy disposes. Denials and approval
requirements are structured errors — execution never happens before
the policy allows it.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from computer.actions import ComputerAction

# Process / window-title fragments that are NEVER interactable:
# credential stores, authentication, admin tooling, security software.
DENIED_APP_FRAGMENTS = (
    "keepass", "1password", "lastpass", "bitwarden", "dashlane",
    "password", "credential", "login", "signin", "sign-in", "auth",
    "uac", "consent.exe", "device manager", "devmgmt",
    "group policy", "gpedit", "regedit", "registry editor",
    "services.msc", "task manager", "taskmgr",
    "defender", "antivirus", "firewall", "mcafee", "norton",
    "mmc.exe", "powershell_ise", "admin",
)

# Launch commands for the harmless allowlisted test applications.
APP_LAUNCH_COMMANDS = {
    "notepad": ["notepad.exe"],
    "calc": ["calc.exe"],
    "calculator": ["calc.exe"],
    "mspaint": ["mspaint.exe"],
    "paint": ["mspaint.exe"],
}


class PolicyViolation(ValueError):
    """Structured policy denial (caller must not execute)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _denied_fragment(blob: str) -> Optional[str]:
    lowered = str(blob or "").lower()
    for fragment in DENIED_APP_FRAGMENTS:
        if fragment in lowered:
            return fragment
    return None


def check_application(action: ComputerAction,
                      allowed_apps: List[str]) -> None:
    """Reject denied applications; open_app must name an allowed app."""
    blob = f"{action.app} {action.target}"
    hit = _denied_fragment(blob)
    if hit:
        raise PolicyViolation("APPLICATION_RESTRICTED",
                              f"interaction with {hit!r} is never allowed")
    if action.action == "open_app":
        wanted = str(action.app or "").lower()
        if wanted not in [a.lower() for a in allowed_apps]:
            raise PolicyViolation("APPLICATION_RESTRICTED",
                                  f"application {action.app!r} is not in the "
                                  f"allowed list {sorted(allowed_apps)}")


def check_freshness(action: ComputerAction, max_age_s: float,
                    now: Optional[float] = None) -> None:
    """Sensitive actions need a recent grounding observation."""
    if action.risk == "LOW" or action.action in ("screenshot", "wait"):
        return
    if action.action == "open_app" and action.coordinates is None:
        return  # process-launch grounding is the launch itself
    if not action.observed_at:
        raise PolicyViolation("STALE_OBSERVATION",
                              f"{action.action} needs a grounding observation "
                              f"(none attached); observe first")
    age = (now if now is not None else time.time()) - action.observed_at
    if age < 0 or age > max_age_s:
        raise PolicyViolation("STALE_OBSERVATION",
                              f"observation is {age:.1f}s old "
                              f"(max {max_age_s:.0f}s); re-observe first")


@dataclass
class ApprovalRequest:
    request_id: str
    action: Dict[str, Any]
    risk: str
    app: str
    state: str = "PENDING"  # PENDING | APPROVED | REJECTED | EXPIRED
    created_at: float = field(default_factory=time.time)
    decided_at: float = 0.0


def _signature(action_dict: Dict[str, Any]) -> str:
    parts = [str(action_dict.get("action", "")),
             str(action_dict.get("target", "")),
             str(action_dict.get("coordinates", "")),
             str(action_dict.get("text", ""))[:80],
             str(action_dict.get("key", "")),
             str(action_dict.get("hotkey", "")),
             str(action_dict.get("app", ""))]
    return "|".join(parts)


class ApprovalStore:
    """Thread-safe human-approval ledger (in-memory, explicit only)."""

    def __init__(self, timeout_s: float = 120.0):
        self.timeout_s = float(timeout_s or 120.0)
        self._lock = threading.Lock()
        self._requests: Dict[str, ApprovalRequest] = {}

    def request(self, action: ComputerAction) -> ApprovalRequest:
        with self._lock:
            self._sweep_locked()
            signature = _signature(action.as_dict())
            for req in self._requests.values():
                if (req.state == "PENDING"
                        and _signature(req.action) == signature):
                    return req  # identical request already awaiting decision
            req = ApprovalRequest(request_id=uuid.uuid4().hex[:8],
                                  action=action.as_dict(),
                                  risk=action.risk, app=action.app)
            self._requests[req.request_id] = req
            return req

    def approve(self, request_id: str) -> ApprovalRequest:
        return self._decide(request_id, "APPROVED")

    def reject(self, request_id: str) -> ApprovalRequest:
        return self._decide(request_id, "REJECTED")

    def _decide(self, request_id: str, state: str) -> ApprovalRequest:
        with self._lock:
            req = self._requests.get(request_id, None)
            if req is None:
                raise PolicyViolation("APPROVAL_UNKNOWN",
                                      f"no approval request {request_id!r}")
            self._sweep_locked()
            if req.state != "PENDING":
                return req
            req.state = state
            req.decided_at = time.time()
            return req

    def status(self, request_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            self._sweep_locked()
            return self._requests.get(request_id)

    def pending(self) -> List[ApprovalRequest]:
        with self._lock:
            self._sweep_locked()
            return [r for r in self._requests.values() if r.state == "PENDING"]

    def consume_approved(self, action_dict: Dict[str, Any],
                         max_age_s: float = 300.0) -> str:
        """Consume a fresh APPROVED request matching the action.

        Returns its id, or "" when none exists. One approval executes
        one action: consumed approvals are removed.
        """
        import time as _time

        with self._lock:
            self._sweep_locked()
            wanted = _signature(action_dict)
            now = _time.time()
            for request_id, req in list(self._requests.items()):
                if (req.state == "APPROVED"
                        and _signature(req.action) == wanted
                        and now - req.decided_at <= max_age_s):
                    del self._requests[request_id]
                    return request_id
        return ""

    def _sweep_locked(self) -> None:
        now = time.time()
        for req in self._requests.values():
            if req.state == "PENDING" and now - req.created_at > self.timeout_s:
                req.state = "EXPIRED"
                req.decided_at = now


def decide(action: ComputerAction, allowed_apps: List[str],
           max_age_s: float, approvals: ApprovalStore,
           approval_id: str = "") -> Dict[str, Any]:
    """Full policy gate. Returns an approval receipt, or raises.

    HIGH-risk actions always need an approved request. MEDIUM actions
    need approval only when the caller declares approval_required (the
    autonomous pipeline never does, so MEDIUM executes with policy
    checks but no human round-trip; HIGH is blocked pending approval).
    """
    check_application(action, allowed_apps)
    check_freshness(action, max_age_s)
    if action.risk != "HIGH":
        return {"allowed": True, "approval": "not-required", "risk": action.risk}
    if approval_id:
        req = approvals.status(approval_id)
        if req is None:
            raise PolicyViolation("APPROVAL_UNKNOWN",
                                  f"no approval request {approval_id!r}")
        if req.state == "APPROVED":
            return {"allowed": True, "approval": "approved",
                    "risk": action.risk, "request_id": req.request_id}
        if req.state == "REJECTED":
            raise PolicyViolation("APPROVAL_DENIED",
                                  f"operator rejected {action.action}")
        raise PolicyViolation("APPROVAL_REQUIRED",
                              f"request {req.request_id} still pending")
    pending = approvals.request(action)
    raise PolicyViolation("APPROVAL_REQUIRED",
                          f"HIGH-risk {action.action} needs approval "
                          f"(request {pending.request_id})")
