from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Untrusted-Code Sandbox
Author: Heeran Paul
License: MIT
--------------------------------------------

Isolated execution for generated code (Phase 5). Generated code is
NEVER executed in-process or on the host directly: it is written to a
fresh temp directory and run in a resource-bounded subprocess with a
hard timeout. The subprocess re-executes Python with restricted
standard streams; a crash, timeout or missing output is reported as an
observed failure — never fabricated.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

_RUNNER = '''\
import json, sys, traceback

def main():
    payload = json.loads(sys.stdin.read())
    code = payload["code"]
    tests = payload.get("tests", [])
    results = {"compiled": False, "passed": 0, "failed": 0, "errors": []}
    namespace: dict = {}
    try:
        exec(compile(code, "<generated>", "exec"), namespace)  # noqa: S102
        results["compiled"] = True
    except Exception as exc:
        results["errors"].append(f"compile: {type(exc).__name__}: {exc}")
        print(json.dumps(results))
        return
    for index, test in enumerate(tests):
        label = test.get("name") or f"test_{index + 1}"
        try:
            expression = test["expression"]
            expected = test.get("expected")
            actual = eval(expression, {"__builtins__": __builtins__}, namespace)  # noqa: S307
            ok = (str(actual) == str(expected)) if "expected" in test else bool(actual)
        except Exception as exc:
            results["failed"] += 1
            results["errors"].append(f"{label}: {type(exc).__name__}: {exc}")
            continue
        if ok:
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["errors"].append(f"{label}: expected={expected!r} actual={actual!r}")
    print(json.dumps(results))

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"compiled": False, "passed": 0, "failed": 0,
                          "errors": ["runner crashed"]}))
'''


def run_code_in_sandbox(
    code: str,
    tests: List[Dict[str, Any]],
    timeout_s: float = 20.0,
) -> Dict[str, Any]:
    """Run generated code + expression tests in an isolated subprocess.

    Returns {compiled, passed, failed, errors, timed_out, exit_code}.
    Every failure mode is observable and reported honestly.
    """
    results: Dict[str, Any] = {"compiled": False, "passed": 0, "failed": 0,
                               "errors": [], "timed_out": False, "exit_code": None}
    with tempfile.TemporaryDirectory(prefix="hercule-eval-") as tmp:
        workdir = Path(tmp)
        runner_path = workdir / "_sandbox_runner.py"
        runner_path.write_text(_RUNNER, encoding="utf-8")
        payload = json.dumps({"code": code, "tests": tests})
        try:
            proc = subprocess.run(
                [sys.executable, str(runner_path)],
                input=payload, capture_output=True, text=True,
                timeout=max(1.0, float(timeout_s)), cwd=str(workdir),
                env={"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
                     "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            results["timed_out"] = True
            results["errors"].append(f"sandbox timeout after {timeout_s:.0f}s")
            return results
        except Exception as exc:
            results["errors"].append(f"sandbox spawn failed: {exc}")
            return results
        results["exit_code"] = proc.returncode
        for line in reversed((proc.stdout or "").strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    observed = json.loads(line)
                    results.update({k: observed[k] for k in
                                    ("compiled", "passed", "failed", "errors")
                                    if k in observed})
                    break
                except Exception:
                    continue
        if not results["compiled"] and not results["errors"] and proc.returncode not in (0, None):
            results["errors"].append(f"runner exited {proc.returncode}: {(proc.stderr or '')[:200]}")
    return results


def score_generated_code(
    code: str,
    tests: List[Dict[str, Any]],
    timeout_s: float = 20.0,
) -> float:
    """Compilation + unit-test pass rate; 0.0 when nothing compiled."""
    outcome = run_code_in_sandbox(code, tests, timeout_s=timeout_s)
    if not outcome.get("compiled") or not tests:
        return 0.0
    return round(outcome.get("passed", 0) / len(tests), 3)
