from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Runtime Tester

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import time
from typing import Any, Dict


class RuntimeTester:
    """
    Performs an end-to-end runtime test.

    Tests:

    • Startup
    • Initialization
    • Request processing
    • Response generation
    • Shutdown
    """

    def __init__(self, runtime: Any) -> None:

        self.runtime = runtime

    # --------------------------------------------------

    def run(self) -> Dict[str, Any]:

        report = {

            "startup": False,
            "request": False,
            "response": False,
            "shutdown": False,
            "execution_time": 0.0,
            "error": None,

        }

        start = time.perf_counter()

        try:

            # Startup

            if hasattr(self.runtime, "initialize"):

                self.runtime.initialize()

            elif hasattr(self.runtime, "start"):

                self.runtime.start()

            report["startup"] = True

            # Request

            if hasattr(self.runtime, "process"):

                result = self.runtime.process(
                    "Hello HERCULE"
                )

                report["request"] = True

                if result is not None:

                    report["response"] = True

            elif hasattr(self.runtime, "execute"):

                result = self.runtime.execute(
                    "Hello HERCULE"
                )

                report["request"] = True

                if result is not None:

                    report["response"] = True

            # Shutdown

            if hasattr(self.runtime, "shutdown"):

                self.runtime.shutdown()

            elif hasattr(self.runtime, "stop"):

                self.runtime.stop()

            report["shutdown"] = True

        except Exception as exc:

            report["error"] = str(exc)

        report["execution_time"] = round(

            time.perf_counter() - start,

            3,

        )

        return report

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.run()

        print("\n========== Runtime Tester ==========\n")

        print(f"Startup   : {report['startup']}")
        print(f"Request   : {report['request']}")
        print(f"Response  : {report['response']}")
        print(f"Shutdown  : {report['shutdown']}")
        print(f"Time      : {report['execution_time']} sec")

        if report["error"]:

            print(f"\nError : {report['error']}")

        print("\n====================================\n")