from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Capability Registry
Author: Heeran Paul
License: MIT
--------------------------------------------

Authoritative CAPABILITY -> providers mapping. Providers are tools
(abilities) or agents; registration validates names against the live
registries, so phantom providers are rejected. Health and permissions
are read live from the owning managers — never cached assumptions.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from cognition.capabilities.capability import Capability, coerce_all


@dataclass
class CapabilityProvider:
    kind: str  # "tool" | "agent"
    name: str
    capabilities: List[Capability] = field(default_factory=list)
    environments: Set[str] = field(default_factory=lambda: {"default"})
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "capabilities": [c.value for c in self.capabilities],
            "environments": sorted(self.environments),
            "metadata": dict(self.metadata),
        }


# Default tool mapping for the built-in abilities (v1.1 adds vision).
DEFAULT_TOOL_CAPABILITIES: Dict[str, List[str]] = {
    "files": ["FILE_READ", "FILE_WRITE"],
    "terminal": ["TERMINAL_EXECUTE"],
    "search": ["WEB_SEARCH", "KNOWLEDGE_RETRIEVAL"],
    "browser": ["BROWSER_USE"],
    "web": ["WEB_SEARCH", "DOCUMENT_READ"],
    "research": ["KNOWLEDGE_RETRIEVAL", "DOCUMENT_READ", "WEB_SEARCH"],
    "coding": ["CODE_EDIT", "CODE_EXECUTION"],
    "mathematics": ["MATH"],
    "calculator": ["MATH"],
    "automation": ["APPLICATION_CONTROL"],
    "networking": ["SYSTEM_OBSERVE"],
    "database": ["DATABASE_READ", "DATABASE_WRITE"],
    "package_manager": ["TERMINAL_EXECUTE", "APPLICATION_CONTROL"],
    "diagnostics": ["SYSTEM_OBSERVE"],
    "media": ["VISION_ANALYSIS", "SPEECH_RECOGNITION", "TEXT_TO_SPEECH"],
    "documents": ["DOCUMENT_READ", "DOCUMENT_WRITE"],
    "system_control": ["SYSTEM_OBSERVE", "APPLICATION_CONTROL"],
    "vision": ["VISION_ANALYSIS"],
    "computer": ["APPLICATION_CONTROL"],
}


class CapabilityRegistry:
    """Authoritative capability -> provider index."""

    def __init__(self):
        self._providers: Dict[str, List[CapabilityProvider]] = {}

    def register_provider(
        self,
        capability: Any,
        kind: str,
        name: str,
        capabilities: Optional[List[Any]] = None,
        environments: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ability_manager=None,
        agent_manager=None,
    ) -> CapabilityProvider:
        capability = capability if isinstance(capability, Capability) else Capability(str(capability).upper())
        if kind not in ("tool", "agent"):
            raise ValueError(f"provider kind must be tool|agent, got {kind!r}")
        if kind == "tool" and ability_manager is not None and ability_manager.get(name) is None:
            raise ValueError(f"unknown tool provider: {name!r}")
        if kind == "agent" and agent_manager is not None and agent_manager.get_agent(name) is None:
            raise ValueError(f"unknown agent provider: {name!r}")
        provided = coerce_all(capabilities or [capability])
        if capability not in provided:
            provided = [capability] + provided
        provider = CapabilityProvider(
            kind=kind, name=name, capabilities=provided,
            environments=set(environments or {"default"}), metadata=dict(metadata or {}),
        )
        bucket = self._providers.setdefault(capability.value, [])
        if any(p.kind == kind and p.name == name for p in bucket):
            raise ValueError(f"duplicate provider {kind}:{name} for {capability.value}")
        bucket.append(provider)
        return provider

    def register_default_tools(self, ability_manager=None) -> int:
        count = 0
        for tool_name, caps in DEFAULT_TOOL_CAPABILITIES.items():
            if ability_manager is not None and ability_manager.get(tool_name) is None:
                continue  # only map tools that actually exist
            for cap in coerce_all(caps):
                try:
                    self.register_provider(cap, "tool", tool_name, caps)
                    count += 1
                except ValueError:
                    pass  # already mapped
        return count

    def providers_for(self, capability: Any, environment: str = "default") -> List[CapabilityProvider]:
        capability = capability if isinstance(capability, Capability) else Capability(str(capability).upper())
        # "default" providers are environment-agnostic and visible
        # everywhere; environment-tagged providers (simulation, hardware)
        # appear only in their environment. Physical capabilities are
        # therefore never exposed inside simulation unless explicitly
        # tagged for it.
        return [p for p in self._providers.get(capability.value, [])
                if environment in p.environments or "default" in p.environments]

    def capabilities(self) -> List[str]:
        return sorted(self._providers)

    def provider_health(self, provider: CapabilityProvider, ability_manager=None, agent_manager=None) -> Dict[str, Any]:
        """Live health: tools via enabled flag, agents via registry state."""
        if provider.kind == "tool" and ability_manager is not None:
            ability = ability_manager.get(provider.name)
            if ability is None:
                return {"state": "UNAVAILABLE", "reason": "not registered"}
            state = "READY" if getattr(ability, "enabled", True) else "UNAVAILABLE"
            return {"state": state, "enabled": bool(getattr(ability, "enabled", True))}
        if provider.kind == "agent" and agent_manager is not None:
            agent = agent_manager.get_agent(provider.name)
            if agent is None:
                return {"state": "UNAVAILABLE", "reason": "not registered"}
            state = str(getattr(getattr(agent, "state", None), "name", getattr(agent, "state", "READY"))).upper()
            mapping = {"READY": "READY", "IDLE": "READY", "BUSY": "READY", "THINKING": "READY",
                       "EXECUTING": "READY", "WAITING": "READY", "PAUSED": "DEGRADED",
                       "INITIALIZING": "LOADING", "ERROR": "FAILED", "TERMINATED": "UNAVAILABLE",
                       "SHUTTING_DOWN": "UNAVAILABLE", "OFFLINE": "UNAVAILABLE"}
            return {"state": mapping.get(state, state), "agent_state": state}
        return {"state": "READY", "reason": "no manager bound"}

    def snapshot(
        self,
        ability_manager=None,
        agent_manager=None,
        policy_manager=None,
        environment: str = "default",
    ) -> Dict[str, Any]:
        """Capability -> providers + live health + policy risk."""
        snap: Dict[str, Any] = {}
        for capability in self.capabilities():
            entries = []
            for provider in self.providers_for(Capability(capability), environment):
                health = self.provider_health(provider, ability_manager, agent_manager)
                risk = ""
                if policy_manager is not None:
                    risk = str(getattr(policy_manager, "risk_map", {}).get(capability, ""))
                entries.append({**provider.as_dict(), "health": health, "policy_risk": risk})
            snap[capability] = entries
        return snap
