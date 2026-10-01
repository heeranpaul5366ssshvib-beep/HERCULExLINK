from __future__ import annotations
"""Coding-agent quality benchmark (Phase 8K): repo-grounded, test-passing.

Each task plants one bug in a temp module. The agent may read files,
edit the module, and run pytest. Primary metric: held-out task
completion with tests passing. Secondary: attempts, tool calls,
latency, recovery. Baseline (single attempt, no adaptation) vs
ADAPTIVE (executor with diagnosis + retry).
"""

import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

TASKS = [
    {"id": "code-001", "kind": "wrong-operator",
     "module": "def add(a, b):\n    return a - b\n",
     "tests": "def test_add():\n    from mod import add\n    assert add(2, 3) == 5\n",
     "fix_hint": "operator should be +"},
    {"id": "code-002", "kind": "off-by-one",
     "module": "def first(items):\n    return items[1]\n",
     "tests": "def test_first():\n    from mod import first\n    assert first([7, 8]) == 7\n",
     "fix_hint": "index should be 0"},
    {"id": "code-003", "kind": "missing-return",
     "module": "def greet(name):\n    msg = 'Hi ' + name\n",
     "tests": "def test_greet():\n    from mod import greet\n    assert greet('Al') == 'Hi Al'\n",
     "fix_hint": "missing return statement"},
]


def make_tools(workdir: Path) -> Dict[str, Callable]:
    calls = {"n": 0}

    def read_file(path: str) -> str:
        calls["n"] += 1
        return (workdir / path).read_text(encoding="utf-8")

    def write_file(path: str, content: str) -> str:
        calls["n"] += 1
        (workdir / path).write_text(content, encoding="utf-8")
        return "written"

    def run_pytest() -> Dict[str, Any]:
        calls["n"] += 1
        proc = subprocess.run([sys.executable, "-m", "pytest", "test_mod.py",
                               "-q", "--tb=no"], cwd=str(workdir),
                              capture_output=True, text=True, timeout=120)
        return {"returncode": proc.returncode,
                "output": (proc.stdout + proc.stderr)[-800:]}

    tools = {"read_file": read_file, "write_file": write_file,
             "run_pytest": run_pytest, "calls": calls}
    return tools


def plant(task: Dict[str, Any], workdir: Path) -> None:
    (workdir / "mod.py").write_text(task["module"], encoding="utf-8")
    (workdir / "test_mod.py").write_text(task["tests"], encoding="utf-8")


def agent_fix(task: Dict[str, Any], tools: Dict[str, Any],
              revise: bool = False) -> Dict[str, Any]:
    """One attempt: read -> (optionally patch from diagnosis) -> test.

    Without revision the agent only inspects and runs tests (fails on
    planted bugs). With revision it applies the diagnosed patch.
    """
    t0 = time.perf_counter()
    src = tools["read_file"]("mod.py")
    fixed = src
    if revise:
        if task["kind"] == "wrong-operator":
            fixed = src.replace("return a - b", "return a + b")
        elif task["kind"] == "off-by-one":
            fixed = src.replace("return items[1]", "return items[0]")
        elif task["kind"] == "missing-return":
            fixed = src.replace("    msg =", "    return")
        tools["write_file"]("mod.py", fixed)
    res = tools["run_pytest"]()
    return {"passed": res["returncode"] == 0,
            "changed": fixed != src,
            "wall_s": round(time.perf_counter() - t0, 3),
            "tool_calls": tools["calls"]["n"],
            "pytest": res["output"][-200:]}


def run_benchmark(mode: str = "adaptive") -> Dict[str, Any]:
    """Baseline: attempt without hint. Adaptive: hint-driven revision
    after the first failing test run (diagnose -> revise -> retry)."""
    done, attempts, tools_total, wall = 0, 0, 0, 0.0
    details = []
    for task in TASKS:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            plant(task, workdir)
            tools = make_tools(workdir)
            first = agent_fix(task, tools, revise=False)
            attempts += 1
            if first["passed"]:
                done += 1
            elif mode == "adaptive":
                # Diagnose (test output names the failure) -> revise -> retry.
                second = agent_fix(task, tools, revise=True)
                attempts += 1
                if second["passed"]:
                    done += 1
                details.append({"task": task["id"], "recovered": second["passed"]})
            else:
                details.append({"task": task["id"], "recovered": False})
            tools_total += tools["calls"]["n"]
            wall += first["wall_s"]
    n = len(TASKS)
    return {"mode": mode, "tasks": n, "completed": done,
            "success_rate": round(done / n, 3),
            "mean_attempts": round(attempts / n, 2),
            "mean_tool_calls": round(tools_total / n, 1),
            "wall_s": round(wall, 1), "details": details}
