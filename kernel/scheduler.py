from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Scheduler
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any


class Scheduler:
    """
    Executes background jobs.
    """

    def __init__(self, max_workers: int = 4) -> None:

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers
        )

    def submit(
        self,
        function: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Future:

        return self._executor.submit(
            function,
            *args,
            **kwargs,
        )

    def shutdown(self, wait: bool = True) -> None:

        self._executor.shutdown(wait=wait)