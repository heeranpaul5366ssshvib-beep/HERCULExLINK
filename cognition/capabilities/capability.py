from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Canonical Capabilities
Author: Heeran Paul
License: MIT
--------------------------------------------

Canonical capability vocabulary. Capabilities express WHAT a task
requires — never which implementation provides it. Structured enums,
not arbitrary strings.
"""

from enum import Enum


class Capability(str, Enum):
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    TERMINAL_EXECUTE = "TERMINAL_EXECUTE"
    BROWSER_USE = "BROWSER_USE"
    WEB_SEARCH = "WEB_SEARCH"
    CODE_EDIT = "CODE_EDIT"
    CODE_EXECUTION = "CODE_EXECUTION"
    DOCUMENT_READ = "DOCUMENT_READ"
    DOCUMENT_WRITE = "DOCUMENT_WRITE"
    KNOWLEDGE_RETRIEVAL = "KNOWLEDGE_RETRIEVAL"
    MATH = "MATH"
    DATABASE_READ = "DATABASE_READ"
    DATABASE_WRITE = "DATABASE_WRITE"
    SYSTEM_OBSERVE = "SYSTEM_OBSERVE"
    APPLICATION_CONTROL = "APPLICATION_CONTROL"
    VISION_ANALYSIS = "VISION_ANALYSIS"
    SPEECH_RECOGNITION = "SPEECH_RECOGNITION"
    TEXT_TO_SPEECH = "TEXT_TO_SPEECH"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# Default risk per capability (planner proposes, policy disposes).
CAPABILITY_RISK = {
    Capability.FILE_READ: RiskLevel.LOW,
    Capability.DOCUMENT_READ: RiskLevel.LOW,
    Capability.KNOWLEDGE_RETRIEVAL: RiskLevel.LOW,
    Capability.MATH: RiskLevel.LOW,
    Capability.SYSTEM_OBSERVE: RiskLevel.LOW,
    Capability.WEB_SEARCH: RiskLevel.MEDIUM,
    Capability.BROWSER_USE: RiskLevel.MEDIUM,
    Capability.DATABASE_READ: RiskLevel.MEDIUM,
    Capability.SPEECH_RECOGNITION: RiskLevel.MEDIUM,
    Capability.TEXT_TO_SPEECH: RiskLevel.MEDIUM,
    Capability.VISION_ANALYSIS: RiskLevel.MEDIUM,
    Capability.FILE_WRITE: RiskLevel.HIGH,
    Capability.DOCUMENT_WRITE: RiskLevel.HIGH,
    Capability.CODE_EDIT: RiskLevel.HIGH,
    Capability.CODE_EXECUTION: RiskLevel.HIGH,
    Capability.TERMINAL_EXECUTE: RiskLevel.HIGH,
    Capability.DATABASE_WRITE: RiskLevel.HIGH,
    Capability.APPLICATION_CONTROL: RiskLevel.HIGH,
}


def coerce_capability(value: str) -> Capability:
    """Parse a capability name loudly; unknown names are rejected."""
    try:
        return Capability(str(value).upper())
    except ValueError:
        raise ValueError(f"unknown capability: {value!r}")


def coerce_all(values) -> list[Capability]:
    seen: list[Capability] = []
    for value in values or []:
        cap = value if isinstance(value, Capability) else coerce_capability(value)
        if cap not in seen:
            seen.append(cap)
    return seen
