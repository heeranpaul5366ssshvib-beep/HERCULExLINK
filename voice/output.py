from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Speech Output - Async Speaker (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Non-blocking speech playback. utterances are serialized through a
single daemon worker so the UI thread never blocks on audio and
overlapping speech is impossible. stop() silences promptly;
mute suppresses output while keeping text responses intact.
"""

import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class Utterance:
    text: str
    utterance_id: str = ""
    done: threading.Event = field(default_factory=threading.Event, repr=False)


class AsyncSpeaker:
    """Serial background speaker over any blocking ``say`` callable."""

    def __init__(self, say: Callable[[str], None],
                 interrupt: Optional[Callable[[], None]] = None):
        self._say = say
        self._interrupt = interrupt
        self._queue: "queue.Queue[Optional[Utterance]]" = queue.Queue()
        self._muted = False
        self._current: Optional[Utterance] = None
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._pump, daemon=True)
        self._worker.start()

    # --------------------------------------------------
    def _pump(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:  # stop sentinel for the in-flight utterance
                with self._lock:
                    current, self._current = self._current, None
                if current is not None:
                    current.done.set()
                continue
            with self._lock:
                if self._muted:
                    item.done.set()
                    continue
                self._current = item
            try:
                self._say(item.text)
            except Exception:
                pass
            finally:
                with self._lock:
                    if self._current is item:
                        self._current = None
                item.done.set()

    # --------------------------------------------------
    def speak_async(self, text: str) -> str:
        """Queue one utterance; returns its id (never blocks)."""
        utterance = Utterance(text=str(text or ""), utterance_id=uuid.uuid4().hex[:8])
        if not utterance.text.strip():
            utterance.done.set()
            return utterance.utterance_id
        self._queue.put(utterance)
        return utterance.utterance_id

    def stop(self) -> Dict[str, Any]:
        """Drop queued speech and interrupt the in-flight utterance."""
        drained = 0
        try:
            while True:
                pending = self._queue.get_nowait()
                drained += 1
                if pending is not None:
                    pending.done.set()
        except queue.Empty:
            pass
        if self._interrupt is not None:
            try:
                self._interrupt()
            except Exception:
                pass
        self._queue.put(None)  # sentinel releases the worker afterwards
        return {"stopped": True, "drained": drained}

    def set_muted(self, muted: bool) -> bool:
        with self._lock:
            self._muted = bool(muted)
            return self._muted

    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted

    @property
    def speaking(self) -> bool:
        with self._lock:
            return self._current is not None or not self._queue.empty()

    @property
    def queued(self) -> int:
        return self._queue.qsize()
