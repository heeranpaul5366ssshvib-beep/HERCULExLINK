from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Application Paths
Author: Heeran Paul
License: MIT
--------------------------------------------

Frozen-aware path resolution + per-user data separation.

Development (``python boot.py``): behavior is byte-identical to the
historical relative paths (``data/...``, ``config/...`` resolved
against the current working directory).

Installed (PyInstaller ``--onedir``): the application directory may
be read-only (Program Files), so

* bundled read-only resources resolve under ``sys._MEIPASS``,
* user-writable state (memory, tasks, logs, config, caches,
  experience data) lives under the per-user application data dir
  (``%LOCALAPPDATA%\\HERCULE`` on Windows, ``~/.hercule`` elsewhere).

Existing environment-variable overrides (HERCULE_TASK_STORE,
HERCULE_MEMORY_DIR, ...) keep working unchanged in both modes.
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("HERCULE.Paths")

APP_NAME = "HERCULE"
APP_ID = "HERCULE AI Operating System"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Directory holding bundled read-only resources."""
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        return Path(meipass)
    here = Path(__file__).resolve().parent
    return here.parent  # <repo>/system -> <repo>


def user_data_dir() -> Path:
    """Per-user writable application data directory (created on demand)."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if os.name == "nt" and local_app_data:
        base = Path(local_app_data) / APP_NAME
    else:
        base = Path.home() / f".{APP_NAME.lower()}"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("cannot create user data dir %s: %s", base, exc)
    return base


def resolve_data_path(relative: str) -> str:
    """Resolve a ``data/...`` style path for the current launch mode.

    Development returns the historical relative path unchanged;
    installed mode redirects into the user data dir so Program Files
    is never written to.
    """
    if is_frozen():
        return str(user_data_dir() / relative)
    return relative


def resolve_config_template() -> Path:
    """Bundled ``hercule.example.json`` template (read-only)."""
    return resource_dir() / "config" / "hercule.example.json"


def user_config_file() -> Path:
    """Per-user ``hercule.json`` (created from template on first run)."""
    return user_data_dir() / "config" / "hercule.json"


def ensure_user_config() -> Path:
    """Copy the bundled template to the user config on first run.

    Never overwrites an existing user config (upgrade-safe).
    Returns the user config path.
    """
    target = user_config_file()
    if target.exists():
        return target
    template = resolve_config_template()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if template.exists():
            target.write_bytes(template.read_bytes())
        else:
            target.write_text("{}\n", encoding="utf-8")
    except Exception as exc:
        logger.warning("cannot create user config %s: %s", target, exc)
    return target


def configure_file_logging() -> Path:
    """Attach the application log file; returns its path.

    Installed mode logs to the user data dir; development keeps the
    historical ``data/logs/hercule.log`` location.
    """
    if is_frozen():
        log_file = user_data_dir() / "logs" / "hercule.log"
    else:
        log_file = Path("data") / "logs" / "hercule.log"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(log_file), encoding="utf-8")
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
    except Exception as exc:
        logger.warning("cannot attach log file %s: %s", log_file, exc)
    return log_file
