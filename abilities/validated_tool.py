from __future__ import annotations

import inspect
from typing import Any, Dict

from abilities.tool_policy import ToolPolicy
from security.permissions.policy_manager import PolicyManager


class ValidatedTool:
    """Tool wrapper that validates input, checks policy, and audits execution."""

    def __init__(self, name: str, capability: str, handler, policy: PolicyManager | None = None, risk: str = "LOW", requires_approval: bool = False):
        self.name = name
        self.capability = capability
        self.handler = handler
        self.policy = policy or PolicyManager()
        self.policy.set_permission(capability, True)
        self.risk = risk.upper()
        self.requires_approval = requires_approval
        self.audit_log = []

    def validate_input(self, **kwargs):
        if not kwargs:
            return True
        for key, value in kwargs.items():
            if value is None:
                raise ValueError(f"Tool argument '{key}' cannot be None.")
        return True

    def execute(self, *args, **kwargs):
        self.validate_input(**kwargs)
        decision = self.policy.evaluate(self.capability, {"risk": self.risk}, actor="tool")
        if not decision["allowed"]:
            raise RuntimeError(f"Policy denied '{self.name}' for capability '{self.capability}'.")
        if decision.get("required_approval") and self.requires_approval:
            raise RuntimeError(f"Approval required before executing '{self.name}'.")
        self.audit_log.append({"tool": self.name, "capability": self.capability, "risk": self.risk, "status": "executing"})
        result = self.handler(*args, **kwargs)
        self.audit_log.append({"tool": self.name, "capability": self.capability, "risk": self.risk, "status": "completed", "result": result})
        return result
