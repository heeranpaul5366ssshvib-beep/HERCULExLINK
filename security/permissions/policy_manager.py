from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    risk: str = "LOW"
    capability: str = ""
    required_approval: bool = False


class PolicyManager:
    """Permission and risk policy decision point for tool/action execution."""

    def __init__(self):
        self.permissions: Dict[str, bool] = {}
        self.risk_map: Dict[str, str] = {
            "FILE_READ": "LOW",
            "FILE_WRITE": "HIGH",
            "TERMINAL_EXECUTE": "HIGH",
            "NETWORK_ACCESS": "MEDIUM",
            "SYSTEM_INFO": "LOW",
            "BROWSER_USE": "MEDIUM",
            "APPLICATION_CONTROL": "HIGH",
        }
        self.audit_log: list[dict[str, Any]] = []

    def set_permission(self, capability: str, allowed: bool):
        self.permissions[capability] = bool(allowed)

    def evaluate(self, capability: str, context: Dict[str, Any] | None = None, actor: str = "system") -> Dict[str, Any]:
        context = context or {}
        risk = context.get("risk") or self.risk_map.get(capability, "LOW")
        required_approval = risk in {"HIGH", "MEDIUM"}
        allowed = bool(self.permissions.get(capability, True))
        reason = "Policy allows the action." if allowed else "Policy denies the action."
        decision = {
            "allowed": allowed,
            "reason": reason,
            "risk": str(risk).upper(),
            "capability": capability,
            "required_approval": required_approval and allowed,
            "actor": actor,
        }
        self.audit_log.append({"actor": actor, "capability": capability, **decision})
        return decision
