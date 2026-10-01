from __future__ import annotations
"""BLAS thread configuration (N4 §7): set BEFORE numpy imports.

Reads ``HERCULE_LM_THREADS`` (explicit wins) or falls back to the
physical core count when detectable, else leaves the backend
default. Must be called before ``import numpy`` takes effect.
"""

import os


def physical_cores() -> int:
    """Best-effort physical core count; 0 when unknown (never raises)."""
    try:
        import subprocess

        out = subprocess.run(
            ["wmic", "cpu", "get", "NumberOfCores", "/value"],
            capture_output=True, text=True, timeout=15)
        for line in str(out.stdout or "").splitlines():
            if "NumberOfCores" in line and "=" in line:
                value = int(line.split("=")[1].strip())
                if value > 0:
                    return value
    except Exception:
        pass
    try:
        logical = int(os.cpu_count() or 0)
        if logical >= 4:
            return max(1, logical // 2)
        return logical
    except Exception:
        return 0


def desired_threads() -> int:
    """Explicit override, else physical cores, else 0 (backend default)."""
    try:
        explicit = int(str(os.environ.get("HERCULE_LM_THREADS", "") or "0").strip())
        if explicit > 0:
            return explicit
    except (TypeError, ValueError):
        pass
    return physical_cores()


def configure_threads() -> int:
    """Export BLAS thread env vars pre-numpy-import. Returns threads (0=default).

    When HERCULE_LM_THREADS is explicitly set, it OVERRIDES any existing
    value (not setdefault) so that explicit user intent wins. When it is
    not set, we only set a default if nothing is already configured.
    """
    threads = desired_threads()
    explicit_env = str(os.environ.get("HERCULE_LM_THREADS", "") or "").strip()
    is_explicit = bool(explicit_env)
    try:
        explicit_val = int(explicit_env) if explicit_env else 0
        is_explicit = explicit_val > 0
    except (TypeError, ValueError):
        is_explicit = False

    if threads > 0:
        for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            if is_explicit:
                os.environ[key] = str(threads)
            else:
                os.environ.setdefault(key, str(threads))
    return threads
