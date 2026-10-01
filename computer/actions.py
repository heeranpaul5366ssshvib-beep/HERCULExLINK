from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Computer Actions (v1.2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Structured computer actions. The model proposes mappings; this module
parses and validates them deterministically. Raw model text is never
executed: coordinates are range-checked against the real screen,
sensitive targets are classified, and anything malformed is rejected
with a structured error (caller must not execute).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SUPPORTED_ACTIONS = (
    "screenshot", "move", "click", "double_click", "right_click",
    "scroll", "type", "press_key", "hotkey", "wait", "open_app",
)

# Virtual-key codes for press_key / hotkey (subset; browser/IME keys excluded).
KEY_MAP = {
    "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
}
for _ch in "abcdefghijklmnopqrstuvwxyz0123456789":
    KEY_MAP.setdefault(_ch, ord(_ch.upper()))

# Hotkey combos that always escalate (window management / run dialogs).
_HIGH_RISK_HOTKEYS = (
    frozenset({"win", "r"}), frozenset({"alt", "f4"}),
    frozenset({"ctrl", "alt", "delete"}), frozenset({"win", "l"}),
    frozenset({"alt", "tab"}),
)


class ActionError(ValueError):
    """Structured action failure (caller must not execute)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class ComputerAction:
    action: str = ""
    target: str = ""
    coordinates: Optional[Tuple[int, int]] = None
    text: str = ""
    key: str = ""
    hotkey: Tuple[str, ...] = ()
    app: str = ""
    amount: int = 0
    seconds: float = 0.0
    reason: str = ""
    risk: str = "LOW"
    observed_at: float = 0.0  # epoch of the grounding observation (0 = none)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "coordinates": list(self.coordinates) if self.coordinates else [],
            "text": self.text,
            "key": self.key,
            "hotkey": list(self.hotkey),
            "app": self.app,
            "amount": self.amount,
            "seconds": self.seconds,
            "reason": self.reason,
            "risk": self.risk,
        }


def classify_risk(action: str, target: str = "", key: str = "",
                  hotkey: Tuple[str, ...] = (), text: str = "",
                  app: str = "") -> str:
    """Deterministic risk table (spec Phase 3)."""
    name = str(action or "").lower()
    blob = f"{target} {text} {app}".lower()
    # HIGH: data destruction, system change, messaging/forms, installs.
    if any(w in blob for w in ("delete", "remove all", "format", "uninstall",
                               "install", "registry", "settings",
                               "password", "credential", "login", "sign in",
                               "send message", "submit form", "payment",
                               "admin", "elevat")):
        return "HIGH"
    if name == "hotkey" and frozenset(h.lower() for h in hotkey) in _HIGH_RISK_HOTKEYS:
        return "HIGH"
    if name == "press_key" and str(key or "").lower() in ("delete",):
        return "HIGH"
    # MEDIUM: typing, clicking, opening apps, keys.
    if name in ("click", "double_click", "right_click", "type",
                "open_app", "press_key", "hotkey"):
        return "MEDIUM"
    # LOW: observation + pointer motion + scroll + wait.
    return "LOW"


def parse_action(data: Dict[str, Any]) -> ComputerAction:
    """Parse a proposed mapping into a ComputerAction (no execution)."""
    if not isinstance(data, dict):
        raise ActionError("INVALID_ACTION", "action must be a mapping")
    name = str(data.get("action", "") or "").strip().lower().replace("-", "_")
    if name not in SUPPORTED_ACTIONS:
        raise ActionError("INVALID_ACTION",
                          f"unsupported action {str(data.get('action', ''))!r} "
                          f"(supported: {sorted(SUPPORTED_ACTIONS)})")
    coords: Optional[Tuple[int, int]] = None
    raw_coords = data.get("coordinates", data.get("coordinate", []))
    if raw_coords not in (None, "", []):
        try:
            x, y = list(raw_coords)[:2]
            coords = (int(x), int(y))
        except (TypeError, ValueError):
            raise ActionError("INVALID_COORDINATES",
                              f"coordinates must be [x, y] integers, got {raw_coords!r}")
    hotkey: Tuple[str, ...] = ()
    raw_hotkey = data.get("hotkey", [])
    if raw_hotkey:
        if not isinstance(raw_hotkey, (list, tuple)) or not raw_hotkey:
            raise ActionError("INVALID_ACTION", "hotkey must be a non-empty key list")
        hotkey = tuple(str(k).strip().lower() for k in raw_hotkey if str(k).strip())
        unknown = [k for k in hotkey if k not in KEY_MAP]
        if unknown:
            raise ActionError("INVALID_ACTION", f"unknown hotkey keys: {unknown}")
        if len(hotkey) > 4:
            raise ActionError("INVALID_ACTION", "hotkey has too many keys (max 4)")
    key = str(data.get("key", "") or "").strip().lower()
    if name == "press_key":
        if not key:
            raise ActionError("INVALID_ACTION", "press_key needs a key")
        if key not in KEY_MAP:
            raise ActionError("INVALID_ACTION", f"unknown key: {key!r}")
    text = str(data.get("text", "") or "")
    if name == "type" and not text.strip():
        raise ActionError("INVALID_ACTION", "type needs non-empty text")
    if name == "type" and len(text) > 2000:
        raise ActionError("INVALID_ACTION", "type text too long (max 2000 chars)")
    app = str(data.get("app", data.get("application", "")) or "").strip().lower()
    if name == "open_app" and not app:
        raise ActionError("INVALID_ACTION", "open_app needs an application name")
    try:
        amount = int(data.get("amount", 0) or 0)
    except (TypeError, ValueError):
        raise ActionError("INVALID_ACTION", "scroll amount must be an integer")
    if name == "scroll" and amount == 0:
        amount = -3  # default: a few lines down
    if abs(amount) > 20:
        raise ActionError("INVALID_ACTION", "scroll amount out of range (max 20)")
    try:
        seconds = float(data.get("seconds", 0.0) or 0.0)
    except (TypeError, ValueError):
        raise ActionError("INVALID_ACTION", "wait seconds must be numeric")
    if name == "wait" and not (0.5 <= seconds <= 30.0):
        raise ActionError("INVALID_ACTION", "wait must be 0.5..30 seconds")
    try:
        observed_at = float(data.get("observed_at", 0.0) or 0.0)
    except (TypeError, ValueError):
        observed_at = 0.0
    risk = classify_risk(name, str(data.get("target", "")),
                         key, hotkey, text, app)
    return ComputerAction(
        action=name,
        target=str(data.get("target", "") or "")[:200],
        coordinates=coords,
        text=text[:2000],
        key=key,
        hotkey=hotkey,
        app=app[:80],
        amount=amount,
        seconds=seconds,
        reason=str(data.get("reason", "") or "")[:300],
        risk=risk,
        observed_at=observed_at,
    )


_ACTION_VERB_RE = re.compile(
    r"(?i)\b(double[\s_-]?click|right[\s_-]?click|click|scroll|type|press|hotkey|"
    r"open|launch|move|screenshot|wait)\b")


def describe_action_kind(text: str) -> str:
    """Best-effort action-kind hint from natural language (grounding and
    coordinates still come from validated inputs/observations only)."""
    lowered = str(text or "").lower()
    if "double" in lowered and "click" in lowered:
        return "double_click"
    if "right" in lowered and "click" in lowered:
        return "click" if "left" in lowered else "right_click"
    match = _ACTION_VERB_RE.search(lowered)
    if not match:
        return ""
    verb = match.group(1).lower().replace("-", "_").replace(" ", "_")
    return {"double_click": "double_click", "right_click": "right_click",
            "click": "click", "scroll": "scroll", "type": "type",
            "press": "press_key", "hotkey": "hotkey", "open": "open_app",
            "launch": "open_app", "move": "move",
            "screenshot": "screenshot", "wait": "wait"}.get(verb, "")


def validate_coordinates(action: ComputerAction,
                         screen: Tuple[int, int]) -> ComputerAction:
    """Range-check coordinates against the real screen (no guessing)."""
    if action.coordinates is None:
        return action
    width, height = int(screen[0]), int(screen[1])
    x, y = action.coordinates
    if not (0 <= x < width and 0 <= y < height):
        raise ActionError("INVALID_COORDINATES",
                          f"({x}, {y}) outside screen {width}x{height}")
    return action
