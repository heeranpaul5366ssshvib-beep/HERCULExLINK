"""
--------------------------------------------
HERCULE AI Operating System
Master Bootstrapper & Self-Healing Engine (boot.py)
Author: Heeran Paul
--------------------------------------------
Automatically heals file structures, import orders,
and launches HERCULE online seamlessly.
"""

import os
import sys
import logging
import time

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("HERCULE.Boot")

REQUEST_LOG = logging.getLogger("HERCULE.RequestLifecycle")


def log_lifecycle(correlation_id, stage, **fields):
    """Structured request lifecycle log: REQUEST→CLASSIFICATION→ROUTE→BRAIN→PLAN→…."""
    detail = " ".join(f"{k}={v}" for k, v in fields.items())
    REQUEST_LOG.info("[%s] %s %s", correlation_id, stage, detail)

def auto_heal_project():
    """Automatically heals missing __init__.py files and future import issues across the board.

    Frozen (installed) apps must never write into Program Files: this is a
    development-only repair walk. When running from a PyInstaller bundle
    (``sys.frozen``) it is a no-op so a read-only install dir or launch
    cwd can never trigger ``WinError 5 Access is denied``.
    """
    try:
        if bool(getattr(sys, "frozen", False)):
            return
    except Exception:
        return
    # 1. Ensure __init__.py files in every directory
    for root, dirs, files in os.walk("."):
        if any(exc in root for exc in [".git", "__pycache__", "data", "docs", "assets", "examples", "tests", ".pytest_cache", "hercule_ai.egg-info", ".venv", ".mypy_cache", ".ruff_cache"]):
            continue
        if root != ".":
            init_path = os.path.join(root, "__init__.py")
            if not os.path.exists(init_path):
                try:
                    safe_root = root.replace("\\", "/")
                    with open(init_path, "w", encoding="utf-8") as f:
                        f.write(f'"""Package initializer for {safe_root}"""\n')
                except Exception:
                    pass

    # 2. Fix future import order in python files automatically
    for root, _, files in os.walk("."):
        if any(exc in root for exc in [".git", "__pycache__", "data", "docs", "assets", ".venv", "hercule_ai.egg-info", ".pytest_cache"]):
            continue
        for file in files:
            if file.endswith(".py" ) and file != "boot.py":
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    # Check if __future__ is present but misplaced
                    future_lines = [l for l in lines if "from __future__ import" in l]
                    if future_lines:
                        first_code_idx = 0
                        for idx, l in enumerate(lines):
                            stripped = l.strip()
                            if stripped and not stripped.startswith("#") and not stripped.startswith('"""') and not stripped.startswith("'''"):
                                first_code_idx = idx
                                break
                        
                        # If a future import appears after actual code lines, clean and re-place it at top
                        has_misplaced = any(idx > first_code_idx for idx, l in enumerate(lines) if "from __future__ import" in l)
                        if has_misplaced:
                            cleaned_lines = [l for l in lines if "from __future__ import" not in l]
                            cleaned_lines = ["from __future__ import annotations\n"] + cleaned_lines
                            with open(filepath, "w", encoding="utf-8") as f:
                                f.writelines(cleaned_lines)
                except Exception:
                    pass

class UniversalFallbackManager:
    """Legacy import-time fallback. DEPRECATED (Phase L).

    It fabricated success responses ("Processed your request ... All
    subsystems operational") without executing anything. The CLI no
    longer uses it: initialization failures now fail loudly, and every
    request flows through Brain.run_cycle with task/policy/
    verification enforced.
    """
    def generate(self, *args, **kwargs):
        raise RuntimeError("UniversalFallbackManager is deprecated; initialize the canonical runtime instead.")

    def chat(self, *args, **kwargs):
        raise RuntimeError("UniversalFallbackManager is deprecated; initialize the canonical runtime instead.")

    def __getattr__(self, name):
        raise RuntimeError(f"UniversalFallbackManager is deprecated (accessed '{name}').")


EXIT_COMMANDS = ("exit", "quit", "shutdown")


def initialize_runtime(embedding_config=None):
    """Initialize HERCULE through the single canonical runtime path.

    Inherits model/embedding configuration, permissions, environment
    mode, logging, observability, memory, and the tool registry from
    RuntimeInitializer — no second initialization system exists.
    """
    sys.path.insert(0, os.getcwd())
    from runtime.initializer import RuntimeInitializer

    initializer = RuntimeInitializer()
    if embedding_config is not None:
        return initializer.initialize(embedding_config=embedding_config)
    return initializer.initialize()


def classify_memory_directive(text):
    """Explicit memory directives (deterministic, no model needed).

    Returns "remember" (store a fact), "recall" (answer from store),
    "session" (previous-session summary), or "" when not a directive.
    Only explicit phrasing matches — never inferred from vague input.
    """
    import re as _re
    stripped = (text or "").strip()
    lowered = stripped.lower()
    if _re.match(r"(?i)^\s*(please\s+)?remember\s+(that\s+)?\S", stripped):
        return "remember"
    if _re.match(r"(?i)^\s*forget\s+(that\s+)?\S", stripped):
        return "forget"
    if _re.match(r"(?i)^\s*what\s+do\s+you\s+remember\b", stripped):
        return "recall"
    if "previous session" in lowered or "last session" in lowered:
        return "session"
    return ""


def classify_request(text):
    """QUESTION vs GOAL/TASK/COMMAND/MEMORY via router + capability inference.

    Conversational (QUESTION): greeting / identity / general question with
    NO inferred capabilities -> Brain.think() only. No tasks, no planning,
    no AutonomousLoop, no self-healing.

    Memory (MEMORY): explicit remember/recall/session directives ->
    Brain memory coordination (durable store, no task lifecycle).

    Task (GOAL/COMMAND): slash commands, capability-bearing requests, or
    known subsystem intents -> Brain.run_cycle(). The CLI never plans;
    Brain does.
    """
    import uuid

    from intelligence.runtime.request_router import RequestRouter, RequestType

    stripped = (text or "").strip()
    correlation_id = f"cli-{uuid.uuid4().hex[:8]}"
    log_lifecycle(correlation_id, "REQUEST", input=stripped[:120])
    if stripped.startswith("/"):
        log_lifecycle(correlation_id, "CLASSIFICATION→ROUTE", kind="COMMAND", reason="slash-command")
        return "COMMAND"
    directive = classify_memory_directive(stripped)
    if directive:
        log_lifecycle(correlation_id, "CLASSIFICATION→ROUTE", kind="MEMORY",
                      reason=f"explicit-{directive}-directive")
        return "MEMORY"
    try:
        detailed = RequestRouter(None).classify_detailed(stripped)
        request_type = detailed.get("type", RequestType.UNKNOWN)
        capabilities = detailed.get("capabilities", [])
        reason = detailed.get("reason", "")
    except Exception as exc:
        log_lifecycle(correlation_id, "CLASSIFICATION→ROUTE", kind="GOAL",
                      reason=f"router-error:{exc}; fail-closed to task path")
        return "GOAL"
    log_lifecycle(correlation_id, "CLASSIFICATION→ROUTE",
                  router_type=request_type.value, capabilities=capabilities, reason=reason)
    if request_type == RequestType.CHAT and not capabilities:
        return "QUESTION"
    # (COMMAND reserved for slash commands; task intents map to GOAL)
    return "GOAL"


class HerculeCli:
    """Deterministic CLI front-end over the canonical Brain path.

    handle_line() performs no I/O so tests can drive it directly;
    format_response() renders the structured contract for display.
    """

    def __init__(self, brain):
        self.brain = brain

    def handle_line(self, text):
        """Route one CLI line: QUESTION -> think, MEMORY -> store/recall,
        else Brain.run_cycle.

        QUESTION/MEMORY paths never create tasks, plans, or healing.
        COMMAND/GOAL path delegates to Brain.run_cycle (authoritative
        autonomous path). Every stage is lifecycle-logged.
        """
        import uuid

        cleaned = (text or "").strip()
        if not cleaned:
            return {"kind": "empty", "status": "ignored"}
        if cleaned.lower() in EXIT_COMMANDS:
            return {"kind": "exit", "status": "exit"}
        if cleaned.lower() in ("/health", "/status"):
            # Safe diagnostics: read-only snapshot, never creates tasks,
            # plans, or model calls.
            return self._health_status()
        correlation_id = f"cli-{uuid.uuid4().hex[:8]}"
        kind = classify_request(cleaned)
        log_lifecycle(correlation_id, "ROUTE→BRAIN", kind=kind, input=cleaned[:120])
        if kind == "MEMORY":
            directive = classify_memory_directive(cleaned)
            try:
                if directive == "remember":
                    outcome = self.brain.remember_fact(cleaned, correlation_id=correlation_id)
                elif directive == "forget":
                    import re as _re
                    topic = _re.sub(r"(?i)^\s*forget\s+(that\s+)?", "", cleaned).strip()[:120]
                    memory = getattr(self.brain.orchestrator, "memory", None)
                    removed = memory.forget_fact(topic) if memory else False
                    outcome = {"status": "forgotten" if removed else "empty",
                               "response": (f"Forgot: {topic}" if removed
                                            else f"I have nothing stored about '{topic}'.")}
                elif directive == "session":
                    outcome = self.brain.recall_session()
                else:
                    import re as _re
                    about = _re.sub(r"(?i)^\s*what\s+do\s+you\s+remember\s*(about\s+)?",
                                    "", cleaned).strip(" ?.")
                    outcome = self.brain.recall_memory(about)
            except Exception as exc:
                log_lifecycle(correlation_id, "RESPONSE", kind=kind, status="failed",
                              subsystem="memory", operation=directive, error=str(exc)[:160])
                return {"kind": kind, "status": "failed", "error": str(exc)[:300],
                        "correlation_id": correlation_id}
            status = outcome.get("status", "")
            if status in ("remembered", "forgotten"):
                log_lifecycle(correlation_id, "RESPONSE", kind=kind, status=status)
                return {"kind": kind, "status": status,
                        "response": outcome.get("response", ""), "correlation_id": correlation_id}
            log_lifecycle(correlation_id, "RESPONSE", kind=kind, status=status or "empty")
            return {"kind": kind, "status": status or "empty",
                    "response": outcome.get("response", outcome.get("error", "")),
                    "correlation_id": correlation_id}
        if kind == "QUESTION":
            try:
                answer = self.brain.think(cleaned)
            except Exception as exc:
                log_lifecycle(correlation_id, "RESPONSE", kind=kind, status="failed",
                              subsystem="brain", operation="think", error=str(exc)[:160])
                return {"kind": kind, "status": "failed", "error": str(exc)[:300],
                        "correlation_id": correlation_id}
            if isinstance(answer, str) and answer.startswith("[HERCULE Error]"):
                log_lifecycle(correlation_id, "RESPONSE", kind=kind, status="failed", error=answer[:160])
                return {"kind": kind, "status": "failed", "error": answer[:300],
                        "correlation_id": correlation_id}
            log_lifecycle(correlation_id, "RESPONSE", kind=kind, status="answered")
            return {"kind": kind, "status": "answered", "response": answer,
                    "correlation_id": correlation_id}
        try:
            report = self.brain.run_cycle(cleaned)
        except Exception as exc:
            log_lifecycle(correlation_id, "RESPONSE", kind=kind, status="failed",
                          subsystem="brain", operation="run_cycle", error=str(exc)[:160])
            return {"kind": kind, "status": "failed", "error": str(exc)[:300],
                    "correlation_id": correlation_id}
        result = {"kind": kind, **report}
        log_lifecycle(correlation_id, "RESPONSE", kind=kind, status=result.get("status"),
                      task_id=result.get("task_id", ""))
        return result

    def _health_status(self):
        """Render the central health report as plain text.

        Read-only: uses live runtime state, creates no tasks and makes
        no model calls. Unavailable sections report UNAVAILABLE, never
        fabricated values.
        """
        try:
            from system.health_report import health_report
        except Exception as exc:
            return {"kind": "STATUS", "status": "failed",
                    "error": f"health report unavailable: {exc}"}
        orchestrator = getattr(self.brain, "orchestrator", None)
        services = {
            "brain": self.brain,
            "orchestrator": orchestrator,
            "models": getattr(orchestrator, "models", None),
            "memory": getattr(orchestrator, "memory", None),
            "security": getattr(orchestrator, "security", None),
        }
        try:
            report = health_report(services)
        except Exception as exc:
            return {"kind": "STATUS", "status": "failed",
                    "error": f"health check failed: {exc}"}
        lines = []
        for section in ("runtime", "brain", "models", "memory", "tasks",
                        "autonomy", "abilities", "security", "ui"):
            detail = report.get(section, {}) or {}
            status = str(detail.get("status", "UNKNOWN"))
            extra = ""
            if section == "models":
                extra = (f" provider={detail.get('provider', 'UNKNOWN')}"
                         f" model={detail.get('default_model', 'UNKNOWN')}")
            elif section == "abilities":
                extra = f" registered={detail.get('registered', 'UNKNOWN')}"
            elif section == "tasks":
                extra = f" queued={detail.get('queued_tracked', 'UNKNOWN')}"
            elif status == "UNAVAILABLE" and detail.get("reason"):
                extra = f" ({detail['reason'][:100]})"
            lines.append(f"{section:10s} {status}{extra}")
        return {"kind": "STATUS", "status": "ok",
                "response": "HERCULE health:\n" + "\n".join(lines)}

    @staticmethod
    def format_response(result):
        """Render a structured result without leaking internals."""
        kind = result.get("kind", "GOAL")
        status = result.get("status", "")
        if kind == "empty":
            return ""
        if kind == "exit":
            return "\nShutting down HERCULE...\nShutdown Complete."
        if kind in ("QUESTION", "MEMORY", "STATUS"):
            if status == "failed":
                return f"[HERCULE Error]: {result.get('error', 'unknown error')}"
            if status == "empty":
                return str(result.get("response", "")) or "[HERCULE] Nothing stored."
            return str(result.get("response", ""))
        if status in ("completed", "partial"):
            summary = result.get("execution_summary", "")
            verification = result.get("verification", {}) or {}
            return (f"[HERCULE {status.upper()}] {summary} "
                    f"(verified steps: {verification.get('passed_steps', 0)}; "
                    f"task {result.get('task_id', '')})")
        error = result.get("error") or result.get("result") or "unknown error"
        return f"[HERCULE FAILED] {error} (task {result.get('task_id', '')})".strip()

def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog="boot.py", description="HERCULE AI Operating System")
    parser.add_argument("--headless", action="store_true",
                        help="run the CLI console instead of the desktop interface")
    parser.add_argument("--gui", action="store_true",
                        help="run the desktop interface (default unless --headless)")
    args = parser.parse_args(argv)

    print("\nInitializing HERCULE Self-Healing Runtime...")
    auto_heal_project()

    try:
        from system.version import __version__ as boot_version
    except Exception:
        boot_version = "1.0.0"
    print("\n============================================================")
    print("        HERCULE AI OPERATING SYSTEM (MASTER ONLINE)")
    print("============================================================")
    print(f"Version : {boot_version} (Autonomous Self-Healing Enabled)")
    print("Status  : ONLINE\n")

    # Initialize through the canonical runtime (no second init system).
    # Any failure here is honest: the CLI refuses to fabricate answers.
    try:
        services = initialize_runtime()
        cli = HerculeCli(services["brain"])
    except Exception as exc:
        print(f"[HERCULE Startup Error]: canonical runtime unavailable: {exc}")
        return 1

    # Autonomy is opt-in (never auto-started); the controller below owns
    # the single worker, and shutdown always stops it cleanly first.
    controller = None
    try:
        if not args.headless:
            # Desktop interface over the same live runtime (no browser/port).
            try:
                from interface.app_controller import HerculeAppController
                from interface.desktop_app import launch
                print("Starting HERCULE desktop interface...\n")
                controller = HerculeAppController(services)
                launch(controller)
                return 0
            except Exception as exc:
                print(f"[HERCULE UI unavailable]: {exc}")
                print("Falling back to headless console. Use --headless to skip the UI.\n")

        brain = services["brain"]
        while True:
            try:
                try:
                    brain.consciousness.set_state("LISTENING", "awaiting input")
                except Exception:
                    pass
                user_input = input("HERCULE > ").strip()
                result = cli.handle_line(user_input)
                if result.get("kind") == "exit":
                    print(cli.format_response(result))
                    break
                if result.get("kind") == "empty":
                    continue
                print(cli.format_response(result))
            except KeyboardInterrupt:
                print("\nShutting down HERCULE...")
                break
            except EOFError:
                print("\nShutting down HERCULE...")
                break
            except Exception as e:
                print(f"[HERCULE Runtime Error]: {e}")
        return 0
    finally:
        # Clean shutdown: stop background autonomy, persist task state.
        try:
            worker = (services.get("autonomy_worker")
                      if isinstance(services, dict) else None)
            if worker is None and controller is not None:
                worker = getattr(controller, "_autonomy_worker", None)
            if worker is not None:
                worker.stop()
                print("Autonomy worker stopped; task state persisted.")
        except Exception as exc:
            print(f"[HERCULE Shutdown Warning]: autonomy stop: {exc}")

if __name__ == "__main__":
    main()