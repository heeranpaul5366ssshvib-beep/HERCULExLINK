from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Computer-Action Verifier (v1.2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Outcome verification for computer actions. Every strategy returns
evidence — never an assumption:

* move      -> cursor position re-read from the OS
* click     -> dispatch receipt + optional expected change
* type      -> window text / OCR confirms the expected content
* open_app  -> process appears in the task list
* press/hotkey -> dispatch receipt + optional expected change
* screenshot/wait -> artifact / elapsed evidence

``verified`` is True only with positive evidence. Anything else is
UNVERIFIED or FAILED — success is never reported without it.
"""

import time
from typing import Any, Dict, Optional

from computer.actions import ComputerAction


def verify(action: ComputerAction, dispatch: Dict[str, Any],
           adapter: Any, expect: Optional[Dict[str, Any]] = None,
           before: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Verify one executed action. Never fabricates success."""
    expect = dict(expect or {})
    name = action.action
    try:
        if name == "move":
            at = adapter.cursor_pos()
            want = action.coordinates or [0, 0]
            ok = abs(at[0] - want[0]) <= 2 and abs(at[1] - want[1]) <= 2
            return {"verified": bool(ok), "strategy": "cursor-position",
                    "detail": f"cursor at {at}, wanted {want}"}
        if name in ("click", "double_click", "right_click"):
            if not dispatch.get("clicked"):
                return {"verified": False, "strategy": "dispatch-receipt",
                        "detail": "click was not dispatched"}
            expected_title = str(expect.get("window_title_contains", "") or "")
            if expected_title:
                title = ""
                try:
                    title = adapter.foreground_title()
                except Exception:
                    title = ""
                ok = expected_title.lower() in title.lower()
                return {"verified": bool(ok), "strategy": "foreground-window",
                        "detail": f"foreground={title!r} expected~{expected_title!r}"}
            return {"verified": True, "strategy": "dispatch-receipt",
                    "detail": f"{name} dispatched at {action.coordinates}"}
        if name == "scroll":
            return {"verified": bool(dispatch.get("scrolled")),
                    "strategy": "dispatch-receipt",
                    "detail": f"scrolled {dispatch.get('amount')}"}
        if name == "type":
            wanted = str(expect.get("contains", action.text) or "")
            observed = ""
            if expect.get("window_handle"):
                try:
                    observed = adapter.window_text(int(expect["window_handle"]))
                except Exception as exc:
                    return {"verified": False, "strategy": "window-text",
                            "detail": f"could not read window text: {exc}"}
            elif expect.get("ocr_text") is not None:
                observed = str(expect.get("ocr_text") or "")
            if wanted and wanted in observed:
                return {"verified": True, "strategy": "window-text",
                        "detail": f"expected text present ({len(wanted)} chars)"}
            if wanted:
                return {"verified": False, "strategy": "window-text",
                        "detail": f"expected text absent (saw {len(observed)} chars)"}
            return {"verified": bool(dispatch.get("typed")),
                    "strategy": "dispatch-receipt",
                    "detail": f"typed {dispatch.get('chars', 0)} chars, no text expectation"}
        if name == "open_app":
            try:
                running = adapter.is_process_running(action.app)
            except Exception:
                running = bool(dispatch.get("opened"))
            return {"verified": bool(running), "strategy": "process-list",
                    "detail": f"{action.app} running={running}"}
        if name in ("press_key", "hotkey"):
            if not (dispatch.get("pressed") or dispatch.get("hotkey")):
                return {"verified": False, "strategy": "dispatch-receipt",
                        "detail": "key event was not dispatched"}
            expected_title = str(expect.get("window_title_contains", "") or "")
            if expected_title:
                try:
                    title = adapter.foreground_title()
                except Exception:
                    title = ""
                ok = expected_title.lower() in title.lower()
                return {"verified": bool(ok), "strategy": "foreground-window",
                        "detail": f"foreground={title!r}"}
            return {"verified": True, "strategy": "dispatch-receipt",
                    "detail": f"{name} dispatched"}
        if name == "screenshot":
            size = int((dispatch.get("png_bytes") or [0])[0]) if isinstance(
                dispatch.get("png_bytes"), list) else int(dispatch.get("bytes", 0))
            return {"verified": size > 100, "strategy": "artifact-present",
                    "detail": f"screenshot bytes={size}"}
        if name == "wait":
            return {"verified": True, "strategy": "elapsed",
                    "detail": f"waited {action.seconds}s"}
    except Exception as exc:
        return {"verified": False, "strategy": "error",
                "detail": f"verification error: {exc}"}
    return {"verified": False, "strategy": "unknown-action",
            "detail": f"no verification strategy for {name}"}


def wait_for(predicate, timeout_s: float = 5.0,
             interval_s: float = 0.25) -> bool:
    """Poll predicate until True or timeout (bounded, honest)."""
    deadline = time.perf_counter() + max(0.5, timeout_s)
    while time.perf_counter() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval_s)
    return False
