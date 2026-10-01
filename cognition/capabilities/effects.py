from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Step Effect Classification
Author: Heeran Paul
License: MIT
--------------------------------------------

Explicit execution semantics per step. Ordered by restrictiveness:

READ_ONLY      no observable effects (safe to skip when verified)
IDEMPOTENT     repeatable with identical outcome; requires a state
               check before replay is trusted
EFFECTFUL      changes the world; replay is at-least-once unless a
               resume policy says otherwise
COMPENSATABLE  effectful, but a declared compensation can undo it
NON_RESUMABLE  must never replay automatically (user intervention or
               restart from a safe checkpoint)

A step may CLAIM a stricter class than its capability default, never
a looser one — false idempotency declarations are rejected at resume.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from cognition.capabilities.capability import Capability

_ORDER = ("READ_ONLY", "IDEMPOTENT", "EFFECTFUL", "COMPENSATABLE", "NON_RESUMABLE")


class EffectClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    IDEMPOTENT = "IDEMPOTENT"
    EFFECTFUL = "EFFECTFUL"
    COMPENSATABLE = "COMPENSATABLE"
    NON_RESUMABLE = "NON_RESUMABLE"


# Conservative capability defaults. Anything that changes persistent
# state is at least EFFECTFUL; only pure reads/compute are weaker.
CAPABILITY_EFFECT_DEFAULTS: Dict[Capability, EffectClass] = {
    Capability.FILE_READ: EffectClass.READ_ONLY,
    Capability.DOCUMENT_READ: EffectClass.READ_ONLY,
    Capability.KNOWLEDGE_RETRIEVAL: EffectClass.READ_ONLY,
    Capability.WEB_SEARCH: EffectClass.READ_ONLY,
    Capability.BROWSER_USE: EffectClass.READ_ONLY,
    Capability.SYSTEM_OBSERVE: EffectClass.READ_ONLY,
    Capability.VISION_ANALYSIS: EffectClass.READ_ONLY,
    Capability.SPEECH_RECOGNITION: EffectClass.READ_ONLY,
    Capability.TEXT_TO_SPEECH: EffectClass.READ_ONLY,
    Capability.MATH: EffectClass.IDEMPOTENT,
    Capability.DATABASE_READ: EffectClass.READ_ONLY,
    Capability.FILE_WRITE: EffectClass.EFFECTFUL,
    Capability.DOCUMENT_WRITE: EffectClass.EFFECTFUL,
    Capability.CODE_EDIT: EffectClass.EFFECTFUL,
    Capability.CODE_EXECUTION: EffectClass.EFFECTFUL,
    Capability.TERMINAL_EXECUTE: EffectClass.NON_RESUMABLE,
    Capability.DATABASE_WRITE: EffectClass.COMPENSATABLE,
    Capability.APPLICATION_CONTROL: EffectClass.EFFECTFUL,
}


def default_effect_for(capabilities: List[Any]) -> EffectClass:
    """Most restrictive default across the step's capabilities."""
    result = EffectClass.READ_ONLY
    for cap in capabilities or []:
        key = cap if isinstance(cap, Capability) else Capability(str(cap).upper())
        candidate = CAPABILITY_EFFECT_DEFAULTS.get(key, EffectClass.EFFECTFUL)
        if _ORDER.index(candidate.value) > _ORDER.index(result.value):
            result = candidate
    return result


def coerce_effect(value: Any) -> EffectClass:
    try:
        return EffectClass(str(value).upper())
    except ValueError:
        raise ValueError(f"unknown effect class: {value!r}")


def claim_allowed(declared: EffectClass, capability_default: EffectClass) -> bool:
    """Declared class must be at least as restrictive as the default."""
    return _ORDER.index(declared.value) >= _ORDER.index(capability_default.value)


def describe_semantics(effect: EffectClass) -> str:
    """Documented delivery semantics per class (never exactly-once)."""
    return {
        EffectClass.READ_ONLY: "at-most-once effects; verified steps may skip",
        EffectClass.IDEMPOTENT: "idempotent retry after a passing state check",
        EffectClass.EFFECTFUL: "at-least-once on replay; duplicates possible",
        EffectClass.COMPENSATABLE: "compensate-then-retry; original effect undone first",
        EffectClass.NON_RESUMABLE: "manual intervention or restart required",
    }[effect]
