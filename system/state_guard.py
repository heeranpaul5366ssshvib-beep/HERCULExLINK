from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Persistent-State Write Guard (UAI Phase M.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Fail-closed protection for test/evaluation runs against the
production-state overwrite incident class: a lazily-resolved save
path silently following ambient configuration back to production.

How it works:

* Inactive by default: production behavior is byte-identical
  (``check_state_write`` returns the path unchanged).
* Active when ``HERCULE_TEST_GUARD=1``. Then ``HERCULE_TEST_STATE_DIR``
  MUST name the test-owned state directory, otherwise every guarded
  write fails closed with an explicit configuration error.
* When active, a guarded write is allowed only when its resolved
  target lives inside the state dir. Anything else raises
  ``StateIsolationError`` naming the attempted path, the active
  state dir, and the relevant environment variables.
* NEVER silently redirects: unexpected production writes raise,
  they are not rerouted.

Guarded call sites: experience save, skill save, task persist,
memory store save, world repository save.
"""

import os
from pathlib import Path

GUARD_ENV = "HERCULE_TEST_GUARD"
STATE_DIR_ENV = "HERCULE_TEST_STATE_DIR"

_KNOWN_STATE_ENVS = (
    "HERCULE_TASK_STORE",
    "HERCULE_MEMORY_DIR",
    "HERCULE_EXPERIENCE_STORE",
    "HERCULE_SKILLS_STORE",
    "HERCULE_WORLD_PATH",
)


class StateIsolationError(RuntimeError):
    """A guarded write escaped (or lacked) test state isolation."""


def guard_active() -> bool:
    return str(os.environ.get(GUARD_ENV, "")).strip().lower() in ("1", "true", "yes", "on")


def active_state_dir() -> str:
    return str(os.environ.get(STATE_DIR_ENV, "") or "").strip()


def check_state_write(path: str, *, owner: str = "") -> str:
    """Vet a persistent-state write target. Returns the path unchanged.

    Raises StateIsolationError when the guard is active and the target
    is not inside the configured test state dir (or when no state dir
    is configured at all — fail closed, never fall back to production).
    """
    text = str(path or "")
    if not guard_active():
        return text
    state_dir = active_state_dir()
    if not state_dir:
        raise StateIsolationError(
            f"refusing {owner or 'state'} write to '{text}': "
            f"{GUARD_ENV}=1 but {STATE_DIR_ENV} is not configured "
            f"(fail-closed; configure an evaluation state directory "
            f"instead of falling back to production)")
    try:
        root = Path(state_dir).resolve()
        target = Path(text).resolve() if Path(text).is_absolute() else (root / text).resolve()
        target.relative_to(root)
        return text
    except StateIsolationError:
        raise
    except Exception:
        pass
    configured = {k: os.environ.get(k, "") for k in _KNOWN_STATE_ENVS}
    raise StateIsolationError(
        f"refusing {owner or 'state'} write to '{text}': outside active "
        f"evaluation state '{state_dir}' "
        f"(source: ambient configuration; relevant env: {configured})")


def describe_isolation() -> dict:
    """Current guard posture for diagnostics (never raises)."""
    try:
        return {
            "guard_active": guard_active(),
            "state_dir": active_state_dir(),
            "state_env": {k: os.environ.get(k, "") for k in _KNOWN_STATE_ENVS},
        }
    except Exception:
        return {"guard_active": False, "state_dir": "", "state_env": {}}
