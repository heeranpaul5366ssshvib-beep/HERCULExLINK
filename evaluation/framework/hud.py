from __future__ import annotations
"""Evaluation progress state for HUD / UI panels (Phase 17).

Read-only snapshot object: the runner's on_task_done callback updates
it; the HUD and the desktop evaluation panel read ``snapshot()`` and
render it. Pure presentation state — it never executes anything.
"""

import threading
import time
from typing import Any, Dict, Optional


class EvalHUDState:
    """Thread-safe progress counters for one evaluation run."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._mode = ""
        self._suite = ""
        self._model = ""
        self._provider = ""
        self._total = 0
        self._done = 0
        self._passed = 0
        self._failed = 0
        self._skipped = 0
        self._errors = 0
        self._timeouts = 0
        self._score_sum = 0.0
        self._scored = 0
        self._current = ""
        self._started_mono = 0.0
        self._elapsed_s = 0.0

    # --------------------------------------------------
    # Runner callbacks (on_task_done signature: TaskResult)
    # --------------------------------------------------
    def start_run(self, mode: str = "", model: str = "", provider: str = "",
                  suite: str = "", total: int = 0) -> None:
        with self._lock:
            self._running = True
            self._mode = mode
            self._model = model
            self._provider = provider
            self._suite = suite
            self._total = int(total)
            self._done = self._passed = self._failed = 0
            self._skipped = self._errors = self._timeouts = 0
            self._score_sum = 0.0
            self._scored = 0
            self._current = ""
            self._started_mono = time.monotonic()
            self._elapsed_s = 0.0

    def update(self, result) -> None:
        with self._lock:
            if not self._running:
                return
            self._done += 1
            self._current = str(getattr(result, "task_id", ""))[:60]
            outcome = str(getattr(result, "outcome", ""))
            if outcome == "passed":
                self._passed += 1
            elif outcome == "failed":
                self._failed += 1
            elif outcome == "skipped":
                self._skipped += 1
            elif outcome == "timeout":
                self._timeouts += 1
                self._failed += 1  # a timed-out task did not pass
            elif outcome == "error":
                self._errors += 1
            try:
                self._score_sum += float(getattr(result, "score", 0.0))
                self._scored += 1
            except (TypeError, ValueError):
                pass
            self._elapsed_s = time.monotonic() - self._started_mono

    def announce_total(self, total: int) -> None:
        with self._lock:
            self._total = int(total)

    def finish_run(self) -> None:
        with self._lock:
            self._running = False
            self._current = ""
            self._elapsed_s = time.monotonic() - self._started_mono if self._started_mono else 0.0

    # --------------------------------------------------
    # Read-only snapshot (HUD + UI panel)
    # --------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            score = round(self._score_sum / self._scored, 3) if self._scored else None
            return {
                "running": self._running,
                "mode": self._mode or "UNKNOWN",
                "suite": self._suite or "UNKNOWN",
                "model": self._model or "UNKNOWN",
                "provider": self._provider or "UNKNOWN",
                "total": self._total,
                "done": self._done,
                "passed": self._passed,
                "failed": self._failed,
                "skipped": self._skipped,
                "errors": self._errors,
                "timeouts": self._timeouts,
                "score": score,
                "current": self._current,
                "elapsed_s": round(self._elapsed_s, 1),
            }

    def hud_text(self) -> str:
        """Compact HUD block, e.g. EVALUATION / TASK 27/100 / PASS 24 / FAIL 3."""
        snap = self.snapshot()
        if not snap["running"] and not snap["done"]:
            return ""
        lines = ["EVALUATION",
                 f"TASK {snap['done']}/{snap['total'] or '?'}" if snap["total"]
                 else f"TASK {snap['done']}",
                 f"PASS {snap['passed']}",
                 f"FAIL {snap['failed']}"]
        if snap["errors"]:
            lines.append(f"ERR {snap['errors']}")
        if snap["timeouts"]:
            lines.append(f"TIMEOUT {snap['timeouts']}")
        return "\n".join(lines)
