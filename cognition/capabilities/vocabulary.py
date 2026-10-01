from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Capability Vocabulary
Author: Heeran Paul
License: MIT
--------------------------------------------

Deterministic, registry-backed vocabulary: aliases that normalize to
canonical capabilities, and explicit capability relationships.
Model-invented aliases are never executable — anything outside this
table (and the registry) is rejected at validation.
"""

from typing import Dict, List

from cognition.capabilities.capability import Capability

# Alias -> canonical capability. Curated, not learned.
ALIASES: Dict[str, Capability] = {
    "read files": Capability.FILE_READ,
    "inspect files": Capability.FILE_READ,
    "open project files": Capability.FILE_READ,
    "look at files": Capability.FILE_READ,
    "write files": Capability.FILE_WRITE,
    "create files": Capability.FILE_WRITE,
    "save files": Capability.FILE_WRITE,
    "run tests": Capability.TERMINAL_EXECUTE,
    "execute tests": Capability.TERMINAL_EXECUTE,
    "run commands": Capability.TERMINAL_EXECUTE,
    "shell commands": Capability.TERMINAL_EXECUTE,
    "search the internet": Capability.WEB_SEARCH,
    "google it": Capability.WEB_SEARCH,
    "do math": Capability.MATH,
    "crunch numbers": Capability.MATH,
    "read documents": Capability.DOCUMENT_READ,
    "summarize documents": Capability.DOCUMENT_READ,
    "read pdfs": Capability.DOCUMENT_READ,
    "query memory": Capability.KNOWLEDGE_RETRIEVAL,
    "recall knowledge": Capability.KNOWLEDGE_RETRIEVAL,
}

# Explicit capability relationships (advisory, never auto-invented).
# Reader capability that usually precedes the key.
CAPABILITY_DEPENDENCIES: Dict[Capability, List[Capability]] = {
    Capability.CODE_EDIT: [Capability.FILE_READ],
    Capability.FILE_WRITE: [Capability.FILE_READ],
    Capability.DOCUMENT_WRITE: [Capability.DOCUMENT_READ],
}


def normalize_name(name: str) -> str:
    """Map an alias or name to its canonical capability string.

    Returns the upper-cased input unchanged when it matches neither —
    the validator (not this table) rejects unknowns observably.
    """
    key = str(name).strip().lower()
    if key in ALIASES:
        return ALIASES[key].value
    return str(name).strip().upper()
