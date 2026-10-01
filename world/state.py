from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World State + Fact Status (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Fact lifecycle: OBSERVED (fresh evidence) -> KNOWN (verified) |
INFERRED (model guess, never authoritative) | UNCERTAIN (weak
evidence) | STALE (superseded or aged out). Inferred facts NEVER
promote automatically: only verified evidence promotes to KNOWN.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class FactStatus(str, Enum):
    OBSERVED = "OBSERVED"
    KNOWN = "KNOWN"
    INFERRED = "INFERRED"
    UNCERTAIN = "UNCERTAIN"
    STALE = "STALE"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def is_stale(last_verified_epoch: float, stale_after_s: float,
             now: float = 0.0) -> bool:
    if not last_verified_epoch:
        return True
    now = now or utc_now_epoch()
    return (now - last_verified_epoch) > max(60.0, stale_after_s)


def promote(status: str, verified: bool) -> str:
    """Next status after new evidence (inferred never self-promotes)."""
    if verified and status in (FactStatus.OBSERVED.value, FactStatus.UNCERTAIN.value,
                               FactStatus.STALE.value, FactStatus.KNOWN.value):
        return FactStatus.KNOWN.value
    if verified:
        # INFERRED + verification -> OBSERVED first (needs a second
        # confirmation for KNOWN); guesses never jump to verified.
        return FactStatus.OBSERVED.value
    return status


def summarize(state: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": state.get("status", FactStatus.UNCERTAIN.value),
            "confidence": float(state.get("confidence", 0.0)),
            "last_verified": state.get("last_verified", "")}
