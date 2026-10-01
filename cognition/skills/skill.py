from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Skill
Author: Heeran Paul
License: MIT
--------------------------------------------

UAI §21 — Skill abstraction.

A skill is a reusable, validated workflow: a named procedure with
declared required capabilities, input/output expectations and a
verification strategy, plus its measured success history.

Skills are data, never executable code: executing a skill means
running its declared steps through the normal validated pipeline
(planner → capability resolution → policy → execution → verification).
Nothing here bypasses validation, permissions or verification.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


SKILL_STATUS_PROPOSED = "proposed"
SKILL_STATUS_VALIDATED = "validated"
SKILL_STATUS_DISABLED = "disabled"


@dataclass
class Skill:
    """A reusable workflow candidate or registered skill."""

    skill_id: str
    description: str
    name: str = ""
    version: str = "1.0.0"
    availability: str = "unknown"
    required_capabilities: List[str] = field(default_factory=list)
    procedure: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    verification: Optional[str] = None
    status: str = SKILL_STATUS_PROPOSED
    source: str = "manual"          # manual | experience | plugin
    success_history: List[bool] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Skill":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    # ------------------------------------------------------------------
    def record_outcome(self, success: bool) -> None:
        """Track a real execution outcome (bounded history)."""
        self.success_history = (self.success_history + [bool(success)])[-50:]

    def success_rate(self) -> Optional[float]:
        if not self.success_history:
            return None
        return round(sum(1.0 for s in self.success_history if s) / len(self.success_history), 3)

    def is_registered(self) -> bool:
        return self.status == SKILL_STATUS_VALIDATED

    @property
    def display_name(self) -> str:
        """Human label: explicit name, else skill_id (never empty)."""
        return self.name or self.skill_id
