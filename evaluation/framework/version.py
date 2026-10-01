from __future__ import annotations
"""Authoritative version lookup for evaluation reports (no duplication)."""


def app_version() -> str:
    try:
        from system.version import __version__
        return str(__version__)
    except Exception:
        return "UNKNOWN"
