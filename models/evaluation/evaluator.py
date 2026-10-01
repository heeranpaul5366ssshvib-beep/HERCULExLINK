from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Model Evaluator
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import time


class ModelEvaluator:

    def benchmark(
        self,
        func,
        *args,
        **kwargs,
    ):

        start = time.perf_counter()

        result = func(
            *args,
            **kwargs,
        )

        elapsed = time.perf_counter() - start

        return {
            "result": result,
            "time": elapsed,
        }