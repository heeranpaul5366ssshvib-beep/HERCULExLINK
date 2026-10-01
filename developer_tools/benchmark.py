from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Benchmark

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import time
from typing import Any, Callable, Dict


class Benchmark:
    """
    Measures the performance of HERCULE
    components.

    Benchmarks:

    • Startup time
    • Function execution
    • Average runtime
    • Multiple iterations
    """

    def __init__(self) -> None:

        self.results: Dict[str, Dict] = {}

    # --------------------------------------------------

    def run(
        self,
        name: str,
        function: Callable[..., Any],
        *args,
        iterations: int = 1,
        **kwargs,
    ) -> Dict:

        durations = []

        output = None

        for _ in range(iterations):

            start = time.perf_counter()

            output = function(
                *args,
                **kwargs,
            )

            end = time.perf_counter()

            durations.append(
                end - start
            )

        report = {

            "iterations": iterations,

            "minimum": round(
                min(durations),
                6,
            ),

            "maximum": round(
                max(durations),
                6,
            ),

            "average": round(
                sum(durations) / len(durations),
                6,
            ),

            "last_result": output,

        }

        self.results[name] = report

        return report

    # --------------------------------------------------

    def get_result(
        self,
        name: str,
    ) -> Dict | None:

        return self.results.get(name)

    # --------------------------------------------------

    def get_all_results(
        self,
    ) -> Dict[str, Dict]:

        return self.results

    # --------------------------------------------------

    def clear(self) -> None:

        self.results.clear()

    # --------------------------------------------------

    def print_report(self) -> None:

        print("\n========== Benchmark ==========\n")

        if not self.results:

            print("No benchmarks executed.\n")
            return

        for name, result in self.results.items():

            print(f"Component : {name}")

            print(
                f"Iterations : {result['iterations']}"
            )

            print(
                f"Average    : {result['average']} sec"
            )

            print(
                f"Minimum    : {result['minimum']} sec"
            )

            print(
                f"Maximum    : {result['maximum']} sec"
            )

            print()

        print("===============================\n")