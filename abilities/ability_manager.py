from __future__ import annotations
from system.guardian_patch import UniversalFallbackMixin
"""
--------------------------------------------
HERCULE AI Operating System
Module: Ability Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from abilities.registry import AbilityRegistry
from security.permissions.policy_manager import PolicyManager
from security.quotas.resource_quota import ResourceQuotaManager, QuotaEnforcer, ResourceQuota

from abilities.terminal.terminal_ability import TerminalAbility
from abilities.files.file_ability import FileAbility
from abilities.search.search_ability import SearchAbility
from abilities.browser.browser_ability import BrowserAbility
from abilities.web.web_ability import WebAbility
from abilities.research.research_ability import ResearchAbility
from abilities.coding.coding_ability import CodingAbility
from abilities.mathematics.mathematics_ability import MathematicsAbility
from abilities.calculator.calculator_ability import CalculatorAbility
from abilities.automation.automation_ability import AutomationAbility
from abilities.networking.networking_ability import NetworkingAbility
from abilities.database.database_ability import DatabaseAbility
from abilities.package_manager.package_manager_ability import PackageManagerAbility
from abilities.diagnostics.diagnostics_ability import DiagnosticsAbility
from abilities.media.media_ability import MediaAbility
from abilities.documents.documents_ability import DocumentAbility
from abilities.system_control.system_control_ability import SystemControlAbility
from abilities.vision.vision_ability import VisionAbility
from abilities.computer.computer_ability import ComputerAbility


import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting an ability."""
    max_calls: int = 100          # max calls per window
    window_seconds: float = 60.0  # time window in seconds
    burst_allowance: int = 10     # additional burst calls allowed


@dataclass
class AbilityRateLimiter:
    """Token bucket rate limiter for abilities."""
    configs: Dict[str, RateLimitConfig] = field(default_factory=dict)
    _tokens: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _last_refill: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def set_limit(self, ability_name: str, config: RateLimitConfig):
        with self._lock:
            self.configs[ability_name] = config
            if ability_name not in self._tokens:
                self._tokens[ability_name] = float(config.max_calls + config.burst_allowance)
                self._last_refill[ability_name] = time.time()

    def check_limit(self, ability_name: str, cost: int = 1) -> tuple[bool, Dict[str, Any]]:
        """
        Check if ability can be called.
        Returns (allowed, info_dict).
        """
        with self._lock:
            config = self.configs.get(ability_name)
            if not config:
                return True, {"allowed": True, "reason": "no limit configured"}

            now = time.time()
            # Refill tokens
            elapsed = now - self._last_refill[ability_name]
            refill_rate = config.max_calls / config.window_seconds
            self._tokens[ability_name] = min(
                config.max_calls + config.burst_allowance,
                self._tokens[ability_name] + elapsed * refill_rate
            )
            self._last_refill[ability_name] = now

            if self._tokens[ability_name] >= cost:
                self._tokens[ability_name] -= cost
                return True, {
                    "allowed": True,
                    "remaining": int(self._tokens[ability_name]),
                    "limit": config.max_calls,
                    "window_seconds": config.window_seconds,
                }
            else:
                return False, {
                    "allowed": False,
                    "reason": f"rate limit exceeded for {ability_name}",
                    "retry_after_seconds": (cost - self._tokens[ability_name]) / refill_rate,
                    "limit": config.max_calls,
                    "window_seconds": config.window_seconds,
                }

    def get_status(self, ability_name: str) -> Dict[str, Any]:
        with self._lock:
            config = self.configs.get(ability_name)
            if not config:
                return {"limited": False}
            return {
                "limited": True,
                "max_calls": config.max_calls,
                "window_seconds": config.window_seconds,
                "burst_allowance": config.burst_allowance,
                "current_tokens": self._tokens.get(ability_name, 0),
            }


class AbilityManager(UniversalFallbackMixin):
    """
    ==========================================
             HERCULE ABILITY MANAGER
    ==========================================

    Central manager for every AI capability.

    Responsible for:

    • Registration
    • Discovery
    • Execution
    • Enable / Disable
    • Health
    • Future plugin abilities
    """

    def __init__(self, policy: PolicyManager | None = None):

        self.registry = AbilityRegistry()
        self.policy = policy or PolicyManager()
        self.audit = []
        self.rate_limiter = AbilityRateLimiter()
        # Default limits for high-risk abilities
        self.rate_limiter.set_limit("terminal", RateLimitConfig(max_calls=20, window_seconds=60, burst_allowance=5))
        self.rate_limiter.set_limit("files", RateLimitConfig(max_calls=100, window_seconds=60, burst_allowance=20))
        self.rate_limiter.set_limit("web", RateLimitConfig(max_calls=30, window_seconds=60, burst_allowance=10))
        self.rate_limiter.set_limit("browser", RateLimitConfig(max_calls=10, window_seconds=60, burst_allowance=2))
        self.rate_limiter.set_limit("coding", RateLimitConfig(max_calls=30, window_seconds=60, burst_allowance=5))
        self.rate_limiter.set_limit("database", RateLimitConfig(max_calls=50, window_seconds=60, burst_allowance=10))
        self.rate_limiter.set_limit("package_manager", RateLimitConfig(max_calls=20, window_seconds=60, burst_allowance=5))
        self.rate_limiter.set_limit("computer", RateLimitConfig(max_calls=10, window_seconds=60, burst_allowance=2))
        
        # Resource quotas
        self.quota_manager = ResourceQuotaManager()
        self.quota_enforcer = QuotaEnforcer(self.quota_manager)

    ##################################################
    # REGISTRATION
    ##################################################

    def register(
        self,
        ability,
    ):
        """Register an ability; duplicates by name are rejected honestly."""
        existing = self.registry.get(getattr(ability, "name", ""))
        if existing is not None and existing is not ability:
            raise ValueError(
                f"Ability '{ability.name}' is already registered; "
                f"unregister it first or pick another name."
            )
        self.registry.register(ability)

    ##################################################

    def unregister(
        self,
        name: str,
    ):

        self.registry.unregister(name)

    ##################################################

    def register_defaults(self):
        """Legacy bulk registration; skips names already present (idempotent).

        Prefer ensure_defaults(); direct register() stays strict and
        rejects duplicates honestly.
        """
        present = set(self.registry.names())
        for ability in (TerminalAbility(), FileAbility(), SearchAbility(),
                        BrowserAbility(), WebAbility(), ResearchAbility(),
                        CodingAbility(), MathematicsAbility(), CalculatorAbility(),
                        AutomationAbility(), NetworkingAbility(), DatabaseAbility(),
                        PackageManagerAbility(), DiagnosticsAbility(), MediaAbility(),
                        DocumentAbility(), SystemControlAbility(), VisionAbility(),
                        ComputerAbility()):
            if ability.name not in present:
                self.register(ability)
                present.add(ability.name)

    def ensure_defaults(self):
        """Register missing default abilities only (idempotent).

        Never overwrites already-registered abilities, so test doubles
        and custom providers keep their registrations.
        """
        present = set(self.registry.names())
        for ability in (TerminalAbility(), FileAbility(), SearchAbility(),
                        BrowserAbility(), WebAbility(), ResearchAbility(),
                        CodingAbility(), MathematicsAbility(), CalculatorAbility(),
                        AutomationAbility(), NetworkingAbility(), DatabaseAbility(),
                        PackageManagerAbility(), DiagnosticsAbility(), MediaAbility(),
                        DocumentAbility(), SystemControlAbility(), VisionAbility(),
                        ComputerAbility()):
            if ability.name not in present:
                self.register(ability)
        return self.count()

    ##################################################
    # EXECUTION
    ##################################################

    def execute(
        self,
        name: str,
        *args,
        **kwargs,
    ) -> Any:
        """Validated execution: capability/ability/permissions/inputs/environment.

        High-risk operations require explicit ``approval_required=True``
        plus ``approved=True`` — otherwise they are denied honestly (never
        executed, never faked). Every stage is observability-logged:
        REQUEST → CAPABILITY → SELECTED ABILITY → PERMISSION → EXECUTION →
        VERIFICATION → RESULT (verification itself runs in step_verifier).
        """
        import logging as _logging
        import time as _time

        _log = _logging.getLogger("HERCULE.RequestLifecycle")
        started = _time.perf_counter()
        ability = self.registry.get(name)

        if ability is None:

            raise ValueError(
                f"Unknown ability: {name}"
            )

        if not ability.enabled:

            raise RuntimeError(
                f"Ability '{name}' is disabled."
            )

        capability = getattr(ability, "permission", getattr(ability, "name", name)).upper()
        required = kwargs.pop("capabilities", None)
        declared = [str(c).upper() for c in (required or [])]
        environment = str(kwargs.pop("environment", "default"))
        approval_required = kwargs.pop("approval_required", False)
        approved = kwargs.pop("approved", False)
        policy = kwargs.pop("policy", self.policy)
        _log.info("REQUEST→CAPABILITY caps=%s SELECTED ABILITY=%s",
                  declared or [capability], name)
        # Canonical capabilities (Phase J): when the caller declares which
        # canonical capabilities this execution requires, each is
        # authorized individually. Absent the declaration, the legacy
        # tool-name check below still applies — nothing is weakened.
        if required:
            for canonical in required:
                decision = policy.evaluate(str(canonical).upper(), {"risk": getattr(ability, "risk", "LOW")}, actor="ability_manager")
                if not decision["allowed"]:
                    raise RuntimeError(f"Permission denied for '{name}' via required capability '{canonical}'.")
        auth = policy.evaluate(capability, {"risk": getattr(ability, "risk", "LOW")}, actor="ability_manager")
        if declared:
            for canonical in declared:
                decision = policy.evaluate(canonical, {"risk": getattr(ability, "risk", "LOW")}, actor="ability_manager")
                if not decision["allowed"]:
                    raise RuntimeError(f"Permission denied for '{name}' via required capability '{canonical}'.")
        _log.info("PERMISSION ability=%s allowed=%s risk=%s", name,
                  auth.get("allowed"), getattr(ability, "risk", "LOW"))
        if not auth["allowed"]:
            raise RuntimeError(f"Permission denied for '{name}' via capability '{capability}'.")
        # High-risk system operations need explicit authorization: the
        # caller must pass approval_required=True AND approved=True.
        if str(getattr(ability, "risk", "LOW")).upper() == "HIGH":
            if not (approval_required and approved):
                raise RuntimeError(
                    f"Approval required before executing high-risk ability '{name}'. "
                    f"Re-invoke with approval_required=True and approved=True.")
        elif approval_required and auth.get("required_approval") and not approved:
            raise RuntimeError(f"Approval required before executing '{name}'.")
        # Environment requirements.
        env_ok = True
        if hasattr(ability, "environment_satisfied"):
            try:
                env_ok = ability.environment_satisfied(environment)
            except Exception:
                env_ok = True
        if not env_ok:
            raise RuntimeError(f"Ability '{name}' unavailable in environment '{environment}'.")
        # Input validation.
        if hasattr(ability, "validate_input"):
            try:
                task_arg = args[0] if args else kwargs.get("task", kwargs.get("input", ""))
                problem = ability.validate_input(task_arg, **kwargs)
            except Exception as exc:
                raise RuntimeError(f"Invalid inputs for '{name}': {exc}")
            if problem:
                raise RuntimeError(f"Invalid inputs for '{name}': {problem}")
        # Rate limiting.
        allowed, rate_info = self.rate_limiter.check_limit(name)
        if not allowed:
            raise RuntimeError(f"Rate limit exceeded for '{name}': {rate_info.get('reason', 'too many requests')}. Retry after {rate_info.get('retry_after_seconds', 0):.1f}s")
        # Attach rate limit info to result if successful
        self.audit.append({"ability": name, "capability": capability, "result": "authorized", "risk": getattr(ability, "risk", "LOW"), "rate_limit": rate_info})
        
        # Resource quota check
        quota_result = self.quota_enforcer.check_and_consume(name)
        self.audit[-1]["quota"] = quota_result

        result = ability.execute(*args, **kwargs)
        latency_ms = round((_time.perf_counter() - started) * 1000.0, 2)
        if isinstance(result, dict) and result.get("error") and str(result.get("status", "")).lower() != "failed":
            result = {**result, "status": "failed"}
        # Consume quota only on successful execution
        if isinstance(result, dict) and result.get("status") != "failed":
            self.quota_enforcer.check_and_consume(name)
        # Structured execution envelope (Phase 6): ability, capability,
        # latency, and verification slot travel with the output. setdefault
        # keeps ability-owned keys authoritative; verification itself is
        # filled downstream by orchestrator.step_verifier, never here.
        if isinstance(result, dict):
            result.setdefault("ability", name)
            result.setdefault("capability", (declared[0] if declared else capability))
            result.setdefault("execution_time_ms", latency_ms)
            result.setdefault("verification", None)
        _log.info("EXECUTION→RESULT ability=%s latency_ms=%.2f result=%s",
                  name, latency_ms,
                  str((result or {}).get("status") if isinstance(result, dict) else type(result).__name__)[:40])
        self.audit.append({"ability": name, "capability": capability, "result": "completed", "payload": result})
        return result

    def describe_all(self):
        """Discovery: structured metadata for every registered ability."""
        out = {}
        for name in self.registry.names():
            ability = self.registry.get(name)
            if hasattr(ability, "metadata"):
                try:
                    out[name] = ability.metadata()
                    continue
                except Exception:
                    pass
            out[name] = {"name": name,
                         "description": getattr(ability, "description", ""),
                         "enabled": bool(getattr(ability, "enabled", True))}
        return out

    ##################################################
    # ENABLE / DISABLE
    ##################################################

    def enable(
        self,
        name: str,
    ):

        ability = self.registry.get(name)

        if ability:

            ability.enable()

    ##################################################

    def disable(
        self,
        name: str,
    ):

        ability = self.registry.get(name)

        if ability:

            ability.disable()

    ##################################################
    # LOOKUP
    ##################################################

    def get(
        self,
        name: str,
    ):

        return self.registry.get(name)

    ##################################################

    def abilities(self):

        return self.registry.names()

    ##################################################

    def exists(
        self,
        name: str,
    ):

        return self.registry.get(name) is not None

    ##################################################

    def lookup_by_capability(self, capability: str, environment: str = "default"):
        """All enabled abilities declaring a capability (name-matched).

        The authoritative capability→provider graph lives in
        cognition.capabilities.registry.CapabilityRegistry; this is the
        manager-local lookup used for discovery and availability checks.
        """
        wanted = str(capability or "").upper()
        found = []
        for name in self.registry.names():
            ability = self.registry.get(name)
            declared = {str(getattr(ability, "capability", "") or "").upper()}
            declared |= {str(p).upper() for p in (getattr(ability, "permissions", None) or [])}
            if wanted not in declared:
                continue
            env_ok = True
            if hasattr(ability, "environment_satisfied"):
                try:
                    env_ok = ability.environment_satisfied(environment)
                except Exception:
                    env_ok = True
            if env_ok:
                found.append(ability)
        return found

    def availability(self, name: str, environment: str = "default"):
        """Structured availability: registered/enabled/environment/permission."""
        ability = self.registry.get(name)
        if ability is None:
            return {"name": name, "available": False, "reason": "not registered"}
        if not getattr(ability, "enabled", True):
            return {"name": name, "available": False, "reason": "disabled"}
        env_ok = True
        if hasattr(ability, "environment_satisfied"):
            try:
                env_ok = ability.environment_satisfied(environment)
            except Exception:
                env_ok = True
        if not env_ok:
            return {"name": name, "available": False,
                    "reason": f"unavailable in environment '{environment}'"}
        allowed, reason = (True, "allowed")
        if hasattr(ability, "check_permissions"):
            try:
                allowed, reason = ability.check_permissions(self.policy)
            except Exception as exc:
                allowed, reason = False, str(exc)[:160]
        return {"name": name, "available": bool(allowed),
                "reason": reason, "risk": getattr(ability, "risk", "LOW"),
                "capability": getattr(ability, "capability", "")}

    ##################################################

    def count(self):

        return len(self.registry.names())

    ##################################################
    # HEALTH
    ##################################################

    def health(self):

        return {

            "registered": self.count(),

            "abilities": self.abilities(),

        }

    ##################################################
    # RESET
    ##################################################

    def clear(self):

        for name in list(self.registry.names()):

            self.unregister(name)

    ##################################################
    # FUTURE FEATURES
    ##################################################

    def load_plugins(self):
        """
        Future:
        Load external ability plugins.
        """
        pass

    ##################################################

    def unload_plugins(self):
        """
        Future:
        Unload plugins.
        """
        pass

    ##################################################

    def discover(self):
        """
        Future:
        Automatically discover abilities.
        """
        pass

    ##################################################

    def reload(self):
        """
        Future:
        Hot reload abilities.
        """
        pass

    ##################################################

    def statistics(self):

        return {

            "total": self.count(),

            "enabled": sum(
                1
                for name in self.abilities()
                if self.get(name).enabled
            ),

            "disabled": sum(
                1
                for name in self.abilities()
                if not self.get(name).enabled
            ),

        }