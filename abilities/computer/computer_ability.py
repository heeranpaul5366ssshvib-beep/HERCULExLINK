from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Computer Ability (v1.2, controlled)
Author: Heeran Paul
License: MIT
--------------------------------------------

Single-action computer control inside the existing ability pipeline
(capability -> permission -> execution -> verification). Structured
proposals only: dict tasks (or inputs) carrying explicit action
fields. Coordinates are validated against the real screen and
sensitive actions require a fresh grounding observation; HIGH-risk
actions additionally require a consumed human approval. The ability
never clicks, types, or launches anything the policy has not allowed.
"""

import re as _re
import time as _time

from abilities.base_ability import BaseAbility
from computer.actions import ComputerAction, describe_action_kind, parse_action


def _shared_controller():
    from computer.controller import shared_controller

    return shared_controller()


class ComputerAbility(BaseAbility):

    def __init__(self, controller=None):

        super().__init__(
            "computer",
            "Controlled desktop interaction: pointer, click, type, keys, apps (explicit only)",
            capability="APPLICATION_CONTROL",
            inputs={"action": "screenshot|move|click|double_click|right_click|scroll|type|press_key|hotkey|wait|open_app",
                    "target": "visual target description",
                    "coordinates": "[x, y] validated screen pixels",
                    "text": "text for type", "key": "key for press_key",
                    "hotkey": "key list", "app": "allowlisted application",
                    "approval_id": "approved request id (HIGH-risk)"},
            outputs={"action": "executed action", "verification": "evidence"},
            permissions=["APPLICATION_CONTROL"],
            environments={"default"},
            verification="dispatch receipt + outcome evidence per strategy",
            timeout_s=60,
            risk="MEDIUM",
        )
        self._controller = controller

    def _controller_or_shared(self):
        return self._controller if self._controller is not None else _shared_controller()

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            if not str(task.get("action", "") or "").strip() and not kwargs.get("action"):
                # Natural-language step text may still name a computer action.
                kind = describe_action_kind(str(task.get("description", "")))
                if not kind:
                    return "computer action needs an action field or action language"
                return ""
            return ""
        text = str(task or "")
        if not text.strip() and not kwargs.get("action"):
            return "empty computer request"
        return ""

    def execute(self, task="", context=None, **kwargs):
        from computer.policy import ApprovalStore  # noqa: F401 (explicit policy path)

        proposal: dict = {}
        text = ""
        approval_id = str(kwargs.pop("approval_id", "") or "")
        if isinstance(task, dict):
            text = str(task.get("description", task.get("goal", "")))
            for key in ("action", "target", "coordinates", "coordinate",
                        "text", "key", "hotkey", "app", "application",
                        "amount", "seconds", "reason", "observed_at",
                        "approval_id"):
                if task.get(key) not in (None, ""):
                    proposal[key] = task[key]
            inputs = task.get("inputs") if isinstance(task.get("inputs"), dict) else {}
            for key, value in (inputs or {}).items():
                if key not in proposal and value not in (None, ""):
                    proposal[key] = value
        else:
            text = str(task or "")
        for key in ("action", "target", "coordinates", "text", "key",
                    "hotkey", "app", "amount", "seconds", "reason",
                    "observed_at"):
            if key not in proposal and kwargs.get(key) not in (None, ""):
                proposal[key] = kwargs[key]
        if "app" not in proposal and proposal.get("application"):
            proposal["app"] = proposal.pop("application")
        if not str(proposal.get("action", "") or "").strip():
            kind = describe_action_kind(text)
            if not kind:
                return {"status": "failed",
                        "error": "no computer action specified"}
            proposal["action"] = kind
            if kind == "type" and not str(proposal.get("text", "") or "").strip():
                quoted = _re.search(r"['\"]([^'\"]+)['\"]", text)
                proposal["text"] = (quoted.group(1) if quoted else "")
            if kind == "open_app" and not proposal.get("app"):
                match = _re.search(r"(?i)open\s+(?:the\s+)?([a-z0-9 ]+)", text)
                proposal["app"] = (match.group(1).strip().lower() if match else "")
        if not approval_id:
            approval_id = str(proposal.pop("approval_id", "") or "")
        controller = self._controller_or_shared()
        if not controller.config.enabled:
            return {"status": "failed", "action": proposal.get("action", ""),
                    "error": "computer control is disabled (opt-in: HERCULE_COMPUTER_ENABLED=1)"}
        # Fresh grounding for sensitive actions: attach the controller's
        # latest observation timestamp when the caller gave none.
        try:
            probe = parse_action(dict(proposal))
        except Exception as error:
            code = getattr(error, "code", "INVALID_ACTION")
            return {"status": "failed", "error": str(error)[:300], "code": code}
        if probe.risk != "LOW" and not float(proposal.get("observed_at", 0.0) or 0.0):
            last = getattr(controller, "_last_observation", None) or {}
            try:
                age = _time.time() - float(last.get("at", 0))
                if age <= controller.config.observation_max_age_s:
                    proposal["observed_at"] = float(last.get("at", 0))
            except Exception:
                pass
        # Consume a matching human approval when the caller references none
        # explicitly (approve-then-retry UX: approve in UI, re-issue command).
        if not approval_id and probe.risk == "HIGH":
            try:
                candidate = dict(proposal)
                approval_id = controller.approvals.consume_approved(
                    {**probe.as_dict(), **{k: v for k, v in candidate.items()
                                           if k in probe.as_dict()}})
            except Exception:
                approval_id = ""
        try:
            screen = controller.adapter.screen_size()
        except Exception as error:
            return {"status": "failed", "action": probe.action,
                    "error": f"screen unavailable: {error}"[:300]}
        result = controller.run_action(proposal, approval_id=approval_id,
                                       screen=screen)
        if isinstance(result, dict) and result.get("status") == "completed":
            return {"status": "success", "action": result.get("action", {}),
                    "verification": result.get("verification", {}),
                    "content": f"computer {probe.action} verified"}
        error = str((result or {}).get("error", "computer action failed"))[:300]
        out = {"status": "failed", "action": (result or {}).get("action", {}),
               "error": error}
        for key in ("code", "verification"):
            if (result or {}).get(key) is not None:
                out[key] = result[key]
        return out
