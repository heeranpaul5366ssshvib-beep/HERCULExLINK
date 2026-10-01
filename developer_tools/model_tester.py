from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Model Tester

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import time
from typing import Any, Dict


class ModelTester:
    """
    Tests AI model availability and functionality.

    Checks:

    • Model initialization
    • Model loading
    • Inference
    • Response time
    • Basic health
    """

    def __init__(self, model_manager) -> None:

        self.model_manager = model_manager

    # --------------------------------------------------

    def run(self) -> Dict[str, Any]:

        report = {
            "connected": False,
            "response_time": None,
            "response": None,
            "error": None,
        }

        try:

            start = time.perf_counter()

            response = self.model_manager.generate(
                "Hello"
            )

            end = time.perf_counter()

            report["connected"] = True
            report["response"] = response
            report["response_time"] = round(
                end - start,
                3,
            )

        except Exception as exc:

            report["error"] = str(exc)

        return report

    # --------------------------------------------------

    def print_report(self):

        report = self.run()

        print("\n========== Model Tester ==========\n")

        print(
            f"Connected : {report['connected']}"
        )

        if report["connected"]:

            print(
                f"Response Time : "
                f"{report['response_time']} sec"
            )

            print(
                f"Response : "
                f"{report['response']}"
            )

        else:

            print(
                f"Error : {report['error']}"
            )

        print(
            "\n==================================\n"
        )