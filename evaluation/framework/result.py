from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Result
Author: Heeran Paul
License: MIT
--------------------------------------------

Per-task outcomes, timing breakdown and suite runs. Only measured
values are recorded: metrics that were unavailable stay null/absent
(never fabricated). Results persist under the user data dir
(``%LOCALAPPDATA%\\HERCULE\\evaluation`` in frozen mode, ``data/``
in development) via system.paths.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from evaluation.framework.task import EvalTask, Outcome


@dataclass
class StageTiming:
    """Latency of one pipeline stage in milliseconds."""

    planning_ms: Optional[float] = None
    model_ms: Optional[float] = None
    execution_ms: Optional[float] = None
    verification_ms: Optional[float] = None
    memory_ms: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class TaskResult:
    """Observable outcome of one evaluation task. No reasoning traces."""

    task_id: str
    suite_id: str
    category: str
    outcome: Outcome
    score: float = 0.0
    latency_ms: float = 0.0
    detail: str = ""
    observed: Any = None
    expected: Any = None
    timings: StageTiming = field(default_factory=StageTiming)
    model: str = ""
    provider: str = ""
    safety_class: str = ""
    skipped_reason: str = ""
    llm_calls: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    completed_at: str = ""
    # UAI Phase M4: operational trace harvested from the run_cycle
    # contract (replans, verification counts, steps, skills, policy
    # events). Decisions and outcomes only — never chain-of-thought.
    trace: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        data["timings"] = self.timings.as_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        payload = dict(data or {})
        payload["outcome"] = Outcome(str(payload.get("outcome", "")))
        timings = payload.get("timings") or {}
        payload["timings"] = StageTiming(**{
            k: timings[k] for k in
            ("planning_ms", "model_ms", "execution_ms", "verification_ms", "memory_ms")
            if k in timings and timings[k] is not None})
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class SuiteRun:
    """A recorded run of one suite (or a full multi-suite evaluation)."""

    run_id: str
    scope: str                       # suite_id or "full" / "quick"
    results: List[TaskResult] = field(default_factory=list)
    version: str = ""
    model: str = ""
    provider: str = ""
    started_at: str = ""
    finished_at: str = ""
    wall_ms: float = 0.0
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def counts(self) -> Dict[str, int]:
        tally = {o.value: 0 for o in Outcome}
        for r in self.results:
            tally[r.outcome.value] += 1
        return tally

    def as_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scope": self.scope,
            "version": self.version,
            "model": self.model,
            "provider": self.provider,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "wall_ms": round(self.wall_ms, 3),
            "config": dict(self.config),
            "counts": self.counts,
            "results": [r.as_dict() for r in self.results],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SuiteRun":
        payload = dict(data or {})
        payload["results"] = [TaskResult.from_dict(r) for r in payload.get("results", [])]
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in payload.items() if k in known})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id(scope: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{scope}-{stamp}-{int(time.monotonic() * 1000) % 100000:05d}"


def results_dir() -> Path:
    """Writable results location (frozen-aware, never the install dir)."""
    from system.paths import is_frozen, user_data_dir
    if is_frozen():
        base = user_data_dir() / "evaluation"
    else:
        base = Path("data") / "evaluation"
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_run(run: SuiteRun) -> Path:
    target = results_dir() / f"{run.run_id}.json"
    target.write_text(json.dumps(run.as_dict(), indent=2), encoding="utf-8")
    return target


def load_run(path: Path) -> SuiteRun:
    return SuiteRun.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def list_runs() -> List[Path]:
    root = results_dir()
    return sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def latest_run(scope_prefix: str = "") -> Optional[SuiteRun]:
    for path in list_runs():
        if path.name.startswith(scope_prefix):
            return load_run(path)
    return None
