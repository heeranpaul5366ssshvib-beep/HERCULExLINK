from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Autonomy Levels
Author: Heeran Paul
License: MIT
--------------------------------------------

UAI §27 — Autonomy levels 0-5 with a deterministic gate.

LEVEL 0  conversation only            (no autonomous execution)
LEVEL 1  suggest actions              (no autonomous execution)
LEVEL 2  execute approved actions     (LOW-risk goals only)
LEVEL 3  predefined safe workflows    (MEDIUM-risk goals and below)
LEVEL 4  bounded multi-step autonomy  (HIGH-risk goals require approval)
LEVEL 5  long-running monitored goals (HIGH risk, stricter runtime)

The gate is deterministic and advisory-free: it classifies a goal's
risk from explicit capability keywords (aligned with PolicyManager's
risk_map) and compares it against the level ceiling. It never grants
permissions — the PolicyManager still evaluates every execution; this
only decides whether an autonomous task may be scheduled at all.
"""

from typing import Any, Dict

# Risk ranks (aligned with PolicyManager risk classes).
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

# Ceiling risk rank per autonomy level.
# LEVEL 2/3 admit MEDIUM-risk goals (file creation, installs) because
# interactive-style approved actions are that class; HIGH-risk goals
# need level 4+. Policy approval is still enforced at execution time
# for every MEDIUM/HIGH action regardless of level.
LEVEL_MAX_RISK = {
    0: -1,      # nothing executes
    1: -1,      # suggestions only
    2: 1,       # LOW/MEDIUM risk goals
    3: 1,       # MEDIUM risk and below (predefined safe workflows)
    4: 2,       # HIGH risk goals allowed (approval still required downstream)
    5: 2,       # HIGH risk, monitored
}

LEVEL_NAMES = {
    0: "CONVERSATION_ONLY",
    1: "SUGGEST_ONLY",
    2: "APPROVED_ACTIONS",
    3: "SAFE_WORKFLOWS",
    4: "BOUNDED_AUTONOMY",
    5: "MONITORED_LONGRUN",
}

# Deterministic keyword classifiers (checked against the lowercased goal).
_HIGH_RISK_KEYWORDS = (
    "delete ", "format ", "shutdown", "registry", "admin", "privilege",
    "uninstall", "wipe", "kill process", "erase",
)
_MEDIUM_RISK_KEYWORDS = (
    "write", "create", "modify", "install", "download", "network",
    "browser", "rename", "move ", "execute", "run ",
)

# Runtime ceiling (seconds) per level; None = worker default applies.
LEVEL_MAX_RUNTIME_S = {5: 3600.0}


def normalize_level(value: Any, default: int = 2) -> int:
    """Coerce user/config input into a valid level (0-5); invalid → default."""
    try:
        level = int(value)
    except (TypeError, ValueError):
        return default
    return level if 0 <= level <= 5 else default


def classify_goal_risk(goal: str) -> Dict[str, Any]:
    """Deterministic risk classification for an autonomous goal."""
    text = f" {str(goal or '').strip().lower()} "
    if any(k in text for k in _HIGH_RISK_KEYWORDS):
        risk = "HIGH"
    elif any(k in text for k in _MEDIUM_RISK_KEYWORDS):
        risk = "MEDIUM"
    else:
        risk = "LOW"
    return {"risk": risk, "reason": f"keyword classification for autonomy gate"}


def evaluate_gate(level: int, goal: str) -> Dict[str, Any]:
    """Level gate decision for scheduling an autonomous goal.

    Returns {allowed, level, risk, reason}. Deterministic; never executes.
    """
    level = normalize_level(level)
    verdict = classify_goal_risk(goal)
    risk = verdict["risk"]
    ceiling = LEVEL_MAX_RISK[level]
    if RISK_ORDER[risk] > ceiling:
        return {
            "allowed": False,
            "level": level,
            "risk": risk,
            "reason": (f"goal risk {risk} exceeds autonomy level {level} "
                       f"({LEVEL_NAMES[level]}) ceiling; lower the risk, "
                       f"raise the level, or run the task interactively"),
        }
    return {
        "allowed": True,
        "level": level,
        "risk": risk,
        "reason": f"goal risk {risk} within level {level} ({LEVEL_NAMES[level]}) ceiling",
    }
