from __future__ import annotations
"""Moral/ethical reasoning subsystem (Phase 8F).

Analytical tool only: scenario -> stakeholders / actions /
consequences / principles / tradeoffs / uncertainty -> reasoned
explanation. It NEVER authorizes actions (see §8H: HERCULE Core
PolicyManager decides). No claims of conscience or consciousness.
"""

from cognition.moral_reasoning.analyzer import analyze
from cognition.moral_reasoning.frameworks import FRAMEWORKS

__all__ = ["analyze", "FRAMEWORKS"]
