from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Configuration
Author: Heeran Paul
License: MIT
--------------------------------------------

Configuration for evaluation runs: mode, suite selection, timeouts,
model, parallelism. Environment variables keep parity with the rest of
HERCULE (HERCULE_EVAL_*). Unsafe (ACTIVE safety-class) tasks are never
run concurrently, regardless of configuration.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass
class EvalConfig:
    mode: str = "quick"                     # quick | full | suite
    suites: List[str] = field(default_factory=list)
    model: Optional[str] = None             # None = runtime default
    timeout_s: float = 120.0
    max_tasks: int = 0                      # 0 = no per-suite cap
    parallel: int = 1                       # ACTIVE tasks always serialize
    live: bool = True                       # False = hermetic adapters only
    baseline: bool = False                  # record run as regression baseline
    out_dir: Optional[str] = None
    runs: int = 1                           # repeated executions per task (M8)

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "EvalConfig":
        source = dict(env if env is not None else os.environ)
        def get(name: str, default: str = "") -> str:
            return str(source.get(name, "") or default)
        suites = [s.strip() for s in get("HERCULE_EVAL_SUITES").split(",") if s.strip()]
        return cls(
            mode=get("HERCULE_EVAL_MODE", "quick"),
            suites=suites,
            model=get("HERCULE_EVAL_MODEL") or None,
            timeout_s=_env_float("HERCULE_EVAL_TIMEOUT", 120.0) if env is None else 120.0,
            max_tasks=_env_int("HERCULE_EVAL_MAX_TASKS", 0) if env is None else 0,
            parallel=max(1, _env_int("HERCULE_EVAL_PARALLEL", 1)) if env is None else 1,
            live=get("HERCULE_EVAL_LIVE", "1") not in ("0", "false", "False"),
            runs=max(1, _env_int("HERCULE_EVAL_RUNS", 1)) if env is None else 1,
        )

    def sanitized(self) -> "EvalConfig":
        """Clamp unsafe values (never parallelize ACTIVE tasks)."""
        config = EvalConfig(**self.__dict__)
        config.timeout_s = max(5.0, float(config.timeout_s or 120.0))
        config.parallel = max(1, int(config.parallel or 1))
        config.max_tasks = max(0, int(config.max_tasks or 0))
        config.runs = max(1, int(config.runs or 1))
        if config.mode not in ("quick", "full", "suite"):
            config.mode = "quick"
        return config

    def as_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode, "suites": list(self.suites), "model": self.model,
            "timeout_s": self.timeout_s, "max_tasks": self.max_tasks,
            "parallel": self.parallel, "live": self.live, "baseline": self.baseline,
            "runs": self.runs,
        }
