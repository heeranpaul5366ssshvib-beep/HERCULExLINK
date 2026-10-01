from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ToolPolicy:
    name: str
    capability: str
    risk: str = "LOW"
    requires_approval: bool = False
    allowed: bool = True
    max_retries: int = 2
    timeout_seconds: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "name": self.name,
            "capability": self.capability,
            "risk": self.risk,
            "requires_approval": self.requires_approval,
            "allowed": self.allowed,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "metadata": self.metadata,
        }
