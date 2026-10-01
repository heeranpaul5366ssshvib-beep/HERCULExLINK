from __future__ import annotations
"""Reasoning effort modes (Phase 6I): measurable behaviors, not labels.

Each mode is an explicit compute policy with a token budget, a
validation policy, and a tool-call allowance. The runner records
latency, tokens used, tool calls, and verifier pass rate — the mode's
identity is its MEASURED profile, not its name.
"""

import time
from typing import Any, Callable, Dict

MODES = {
    # max_tokens: generation budget; validate: verifier passes required;
    # max_tools: tool calls allowed (0 = none).
    "FAST": {"max_tokens": 32, "validate": 0, "max_tools": 0},
    "STANDARD": {"max_tokens": 128, "validate": 1, "max_tools": 1},
    "DEEP": {"max_tokens": 512, "validate": 2, "max_tools": 4},
}


def mode_spec(name: str) -> Dict[str, Any]:
    key = str(name).strip().upper()
    if key not in MODES:
        raise ValueError(f"unknown reasoning mode {name!r} (FAST|STANDARD|DEEP)")
    return {"mode": key, **MODES[key]}


def run_with_mode(name: str, generate: Callable[[int], Dict[str, Any]],
                  verify: Callable[[str], Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Execute ``generate(budget)`` under a mode; validate when required.

    ``generate`` returns {"text": str, "tokens": int, "tools": int}.
    Retries (same budget) until ``validate`` passes are recorded or the
    attempt cap (1 + validate) is hit. Returns the measured profile.
    """
    spec = mode_spec(name)
    t0 = time.perf_counter()
    attempts, result = 0, None
    passes = 0
    cap = 1 + int(spec["validate"])
    while attempts < cap:
        attempts += 1
        result = generate(int(spec["max_tokens"]))
        if verify is None or int(spec["validate"]) == 0:
            break
        verdict = verify(str(result.get("text", "")))
        if bool(verdict.get("pass")):
            passes += 1
            if passes >= int(spec["validate"]):
                break
    wall = time.perf_counter() - t0
    result = dict(result or {})
    return {"mode": spec["mode"], "attempts": attempts,
            "tokens": int(result.get("tokens", 0)),
            "tools": int(result.get("tools", 0)),
            "verified_passes": passes,
            "required_passes": int(spec["validate"]),
            "latency_s": round(wall, 3),
            "text": str(result.get("text", ""))[:2000]}
