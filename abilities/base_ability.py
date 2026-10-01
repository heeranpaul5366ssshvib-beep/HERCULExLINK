from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Base Ability
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abc import ABC, abstractmethod


class BaseAbility(ABC):
    """Developer-facing ability interface.

    Subclass and fill structured metadata so the autonomous pipeline can
    discover, match, authorize, execute, and verify without touching Brain:

        class MyAbility(BaseAbility):
            def __init__(self):
                super().__init__(
                    "my_tool", "What it does",
                    capability="MATH", inputs={"expression": "arithmetic string"},
                    outputs={"result": "number"}, permissions=["MATH"],
                    environments={"default"}, verification="result verified by recomputation",
                    timeout_s=30, risk="LOW",
                )
            def execute(self, task, context=None, **kwargs):
                return {"status": "success", "result": ...}  # or {"status": "failed", "error": ...}

    All metadata kwargs are optional (backwards compatible). ``execute``
    must return a structured mapping with ``status`` success|failed —
    never a bare scalar or None — so verification can judge honestly.
    """

    def __init__(

        self,

        name: str,

        description: str,

        capability: str = "",
        inputs: dict | None = None,
        outputs: dict | None = None,
        permissions: list | None = None,
        environments: set | None = None,
        verification: str = "",
        timeout_s: int = 30,
        risk: str = "LOW",

    ):

        self.name = name

        self.description = description

        self.enabled = True

        self.capability = str(capability or "").upper()
        self.inputs = dict(inputs or {})
        self.outputs = dict(outputs or {})
        self.permissions = list(permissions or ([self.capability] if self.capability else []))
        self.environments = set(environments or {"default"})
        self.verification = str(verification or "")
        self.timeout_s = int(timeout_s or 30)
        self.risk = str(risk or "LOW").upper()

    ##################################################

    def metadata(self):
        """Structured metadata for registration/discovery/validation."""
        return {
            "name": self.name,
            "description": self.description,
            "capability": self.capability,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "permissions": list(self.permissions),
            "environments": sorted(self.environments),
            "verification": self.verification,
            "timeout_s": self.timeout_s,
            "risk": self.risk,
            "enabled": self.enabled,
        }

    def describe(self):
        return self.metadata()

    def validate_input(self, task, **kwargs):
        """Pre-execution input check; return "" when valid, else an error."""
        return ""

    def check_environment(self, environment: str = "default"):
        """Environment compatibility (alias over environment_satisfied)."""
        return self.environment_satisfied(environment)

    def environment_satisfied(self, environment: str = "default"):
        return environment in self.environments or "default" in self.environments

    def check_permissions(self, policy_manager=None):
        """Dry-run permission check; returns (allowed, reason) without executing."""
        if policy_manager is None:
            return True, "no policy bound"
        for capability in self.permissions or ([self.capability] if self.capability else []):
            try:
                decision = policy_manager.evaluate(
                    str(capability).upper(), {"risk": self.risk}, actor="ability-check")
            except Exception as exc:
                return False, str(exc)[:160]
            if not decision.get("allowed", True):
                return False, f"permission denied for '{capability}'"
        return True, "allowed"

    def verify(self, result):
        """Default verification: structured success with content.

        Abilities with stronger checks (e.g. recomputation) override this;
        the authoritative per-step gate remains orchestrator.step_verifier.
        """
        if not isinstance(result, dict):
            return False, "result is not a structured mapping"
        if str(result.get("status", "")).lower() != "success":
            return False, str(result.get("error", "ability reported failure"))[:200]
        return True, self.verification or "tool reported success"

    ##################################################

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass

    ##################################################

    def enable(self):

        self.enabled = True

    ##################################################

    def disable(self):

        self.enabled = False

    ##################################################

    def status(self):

        return {

            "name": self.name,

            "description": self.description,

            "enabled": self.enabled,

            "capability": self.capability,

            "risk": self.risk,

            "timeout_s": self.timeout_s,

        }