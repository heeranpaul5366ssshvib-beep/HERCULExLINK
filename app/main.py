from __future__ import annotations
"""HERCULE production entry point (installed Windows application).

Frozen-aware: works from source (``python -m app.main``) and from a
PyInstaller ``--onedir`` bundle (``HERCULE.exe``). Delegates all
cognition to the canonical runtime — no backend logic lives here.

Flow:
  CLI parse -> paths/logging -> runtime init -> health snapshot ->
  first-run status screen (first launch only) -> desktop UI (or
  headless console with ``--headless``) -> clean shutdown.

Crash policy: never terminate silently. Any startup failure writes
diagnostics to the application log and shows an error dialog.
"""

import argparse
import logging
import os
import sys
import traceback

APP_VERSION = "1.0.0"

try:  # single authoritative source; literal fallback keeps frozen boot safe
    from system.version import __version__ as _APP_VERSION

    APP_VERSION = _APP_VERSION
except Exception:
    pass

log = logging.getLogger("HERCULE.App")


# ------------------------------------------------------------------
# Bootstrap: make imports work both from source and frozen bundle
# ------------------------------------------------------------------
def _bootstrap() -> None:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        for candidate in (meipass, os.path.dirname(sys.executable)):
            if candidate and candidate not in sys.path:
                sys.path.insert(0, candidate)
    else:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        if os.getcwd() not in sys.path:
            sys.path.insert(0, os.getcwd())


_bootstrap()

from system.paths import (  # noqa: E402
    configure_file_logging,
    ensure_user_config,
    is_frozen,
    resource_dir,
    user_config_file,
    user_data_dir,
)

LOG_FILE = configure_file_logging()
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")


# ------------------------------------------------------------------
# Startup checks (real health data, never fabricated)
# ------------------------------------------------------------------
def collect_health(services: dict) -> dict:
    """Gather honest subsystem status for the first-run screen."""
    health: dict = {}

    # Runtime
    try:
        brain = services.get("brain")
        health["runtime"] = "ready" if brain is not None else "UNAVAILABLE (no brain)"
    except Exception as exc:
        health["runtime"] = f"UNAVAILABLE ({exc})"

    # Ollama / model (bounded probe via the controller snapshot path)
    try:
        models = services.get("models")
        if models is None:
            health["ollama"] = "UNAVAILABLE (no model manager)"
            health["model"] = "UNKNOWN"
        else:
            model_name = str(getattr(models, "default_model", "") or "UNKNOWN")
            health["model"] = model_name
            available = False
            try:
                router = getattr(models, "router", None)
                adapters = getattr(router, "adapters", {}) or {}
                ollama = adapters.get("ollama")
                if ollama is not None and hasattr(ollama, "health"):
                    info = ollama.health() or {}
                    available = bool(info.get("available", False))
            except Exception:
                available = False
            if available:
                health["ollama"] = "ready"
            else:
                host = getattr(models, "ollama_host", "http://127.0.0.1:11434")
                health["ollama"] = f"UNAVAILABLE (no server at {host})"
    except Exception as exc:
        health["ollama"] = f"UNAVAILABLE ({exc})"
        health.setdefault("model", "UNKNOWN")

    # Memory
    try:
        memory = services.get("memory")
        if memory is None:
            health["memory"] = "UNAVAILABLE"
        else:
            health["memory"] = "ready"
    except Exception as exc:
        health["memory"] = f"UNAVAILABLE ({exc})"

    # Abilities
    try:
        abilities = services.get("abilities")
        count = "?"
        try:
            catalog = abilities.describe_all() if hasattr(abilities, "describe_all") else {}
            count = str(len(catalog or {}))
        except Exception:
            pass
        health["abilities"] = f"ready ({count} tools)" if abilities is not None else "UNAVAILABLE"
    except Exception as exc:
        health["abilities"] = f"UNAVAILABLE ({exc})"

    # Security
    try:
        health["security"] = "ready" if services.get("security") is not None else "UNAVAILABLE"
    except Exception as exc:
        health["security"] = f"UNAVAILABLE ({exc})"

    # HUD (desktop overlay = tkinter availability; honest, not fake)
    try:
        import tkinter  # noqa: F401
        health["hud"] = "ready (desktop overlay)"
    except Exception:
        health["hud"] = "UNAVAILABLE (tkinter missing)"

    health["user_data"] = str(user_data_dir())
    health["log_file"] = str(LOG_FILE)
    # Built-in local model (v2): real readiness, never fabricated.
    try:
        from models.builtin import model_manager as _builtin_store

        installed = _builtin_store.list_installed()
        if installed:
            first = installed[0]
            health["builtin"] = (f"ready ({first['id']}, "
                                 f"{first.get('size', 0) // 1000000}MB GGUF)")
        else:
            health["builtin"] = ("MODEL NOT INSTALLED (no GGUF weights in "
                                 + str(_builtin_store.models_root() / "gguf") + ")")
    except Exception as exc:
        health["builtin"] = f"UNAVAILABLE ({exc})"
    return health


def _first_run_marker() -> "os.PathLike[str]":
    from pathlib import Path

    return Path(str(user_data_dir())) / "first_run_done"


def is_first_run() -> bool:
    try:
        return not _first_run_marker().exists()
    except Exception:
        return False


def mark_first_run_done() -> None:
    try:
        _first_run_marker().write_text("ok\n", encoding="utf-8")
    except Exception:
        pass


def show_first_run_screen(health: dict) -> None:
    """Minimal setup/status dialog. Tkinter only; silently skip headless."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return
    try:
        root = tk.Tk()
    except Exception:
        return
    root.title("HERCULE — First-Run Setup")
    root.configure(bg="#0a0e14")
    root.geometry("560x520")
    ttk_style = ttk.Style(root)
    try:
        ttk_style.theme_use("clam")
    except Exception:
        pass
    title = tk.Label(root, text="HERCULE", bg="#0a0e14", fg="#00d4ff",
                     font=("Consolas", 20, "bold"))
    title.pack(pady=(16, 4))
    subtitle = tk.Label(root, text="HERCULE AI Operating System  v%s" % APP_VERSION,
                        bg="#0a0e14", fg="#5a6b7c", font=("Consolas", 10))
    subtitle.pack(pady=(0, 12))

    order = ["runtime", "ollama", "model", "memory", "abilities", "security", "hud"]
    for key in order:
        value = str(health.get(key, "UNKNOWN"))
        ok = value.startswith("ready")
        color = "#00e676" if ok else "#ffab40"
        row = tk.Label(root, text=f"{key:10s}  {value}", bg="#0a0e14", fg=color,
                       font=("Consolas", 10), anchor="w", justify="left")
        row.pack(fill="x", padx=24, anchor="w")

    ollama_status = str(health.get("ollama", ""))
    if not ollama_status.startswith("ready"):
        note = (
            "\nOllama is unavailable.\n\n"
            "HERCULE still launches: conversation, tasks, abilities,\n"
            "memory and autonomy UI all work.\n"
            "Only model-dependent answers will report an honest\n"
            "model-unavailable error until Ollama is running.\n\n"
            "Install/start Ollama separately, then pull a model:\n"
            "  ollama serve\n  ollama pull llama3.2:3b\n\n"
            "No API keys required. No models are downloaded by HERCULE."
        )
    else:
        note = "\nOllama is reachable. Model-dependent features are enabled."
    tk.Label(root, text=note, bg="#0a0e14", fg="#c9e4f2",
             font=("Consolas", 9), justify="left").pack(padx=24, pady=10, anchor="w")

    tk.Label(root, text=f"Data: {health.get('user_data', '')}\nLog: {health.get('log_file', '')}",
             bg="#0a0e14", fg="#5a6b7c", font=("Consolas", 8),
             justify="left").pack(padx=24, anchor="w")

    btn = tk.Button(root, text="Launch HERCULE", command=root.destroy,
                    bg="#1a2230", fg="#00d4ff", font=("Consolas", 11, "bold"))
    btn.pack(pady=16)
    root.mainloop()


def show_error_dialog(stage: str, category: str, message: str,
                      console_only: bool = False) -> None:
    """Visible failure dialog + log entry. Never silent, never leaks secrets.

    A modal dialog that nobody can see is worse than no dialog: it hangs
    the process forever. Console/headless runs therefore report on
    stderr and return; only display-driven launches show the dialog.
    """
    safe = str(message)[:800]
    log.error("startup failure stage=%s category=%s error=%s", stage, category, safe)
    try:
        with open(str(LOG_FILE), "a", encoding="utf-8") as fh:
            fh.write(f"STARTUP FAILURE stage={stage} category={category}\n{safe}\n")
            fh.write(traceback.format_exc() + "\n")
    except Exception:
        pass
    text = f"HERCULE failed to start.\n\nStage: {stage}\nCategory: {category}\n\n{safe}\n\nSee log:\n{LOG_FILE}"
    if console_only:
        print(text, file=sys.stderr)
        return
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("HERCULE — Startup Error", text)
        root.destroy()
    except Exception:
        print(text, file=sys.stderr)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="HERCULE", description="HERCULE AI Operating System")
    parser.add_argument("--headless", action="store_true", help="run the console instead of the desktop UI")
    parser.add_argument("--gui", action="store_true", help="run the desktop interface (default)")
    parser.add_argument("--status", action="store_true", help="print system status and exit")
    parser.add_argument("--no-first-run", action="store_true", help="skip the first-run setup screen")
    return parser.parse_args(argv)


def initialize_services() -> dict:
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    # Production entry: pre-register default abilities once (idempotent,
    # never overwrites) so health screens and the first task see the
    # real catalog immediately. Dev/test paths keep lazy registration.
    try:
        abilities = services.get("abilities")
        if hasattr(abilities, "ensure_defaults"):
            abilities.ensure_defaults()
    except Exception as exc:
        log.warning("ability pre-registration skipped: %s", exc)
    return services


def run_headless(services: dict) -> int:
    """Console loop reusing the same Brain path as the desktop UI."""
    import importlib.util
    from pathlib import Path

    # Reuse boot.py's CLI routing without its dev-only auto-heal walk.
    boot_path = resource_dir() / "boot.py"
    if not boot_path.exists():
        boot_path = Path(os.getcwd()) / "boot.py"
    spec = importlib.util.spec_from_file_location("hercule_boot_cli", str(boot_path))
    boot_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boot_module)
    cli = boot_module.HerculeCli(services["brain"])
    brain = services["brain"]
    print("HERCULE headless console. Type 'exit' to quit.")
    while True:
        try:
            try:
                brain.consciousness.set_state("LISTENING", "awaiting input")
            except Exception:
                pass
            line = input("HERCULE > ").strip()
            result = cli.handle_line(line)
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
        except Exception as exc:
            print(f"[HERCULE Runtime Error]: {exc}")
    return 0


def run_gui(services: dict) -> int:
    from interface.app_controller import HerculeAppController
    from interface.desktop_app import launch

    controller = HerculeAppController(services)
    try:
        launch(controller)
        return 0
    finally:
        try:
            controller.shutdown_autonomy()
        except Exception:
            pass


def main(argv=None) -> int:
    args = parse_args(argv)
    # Console runs report startup failures on stderr (a modal dialog
    # nobody can see would hang the process forever).
    console_only = bool(args.headless or args.status)
    log.info("HERCULE v%s starting (frozen=%s)", APP_VERSION, is_frozen())
    log.info("resource_dir=%s user_data=%s", resource_dir(), user_data_dir())

    # Startup stage 1: user config (upgrade-safe, never overwritten)
    try:
        ensure_user_config()
        log.info("user config: %s", user_config_file())
    except Exception as exc:
        show_error_dialog("user-config", "config", f"cannot prepare user config: {exc}",
                          console_only=console_only)
        return 1

    # Startup stage 2: runtime
    try:
        services = initialize_services()
    except Exception as exc:
        show_error_dialog("runtime-init", "runtime", f"canonical runtime unavailable: {exc}",
                          console_only=console_only)
        return 1

    # Startup stage 3: health
    try:
        health = collect_health(services)
        for key, value in health.items():
            log.info("health %s=%s", key, value)
    except Exception as exc:
        show_error_dialog("health-check", "runtime", f"health check failed: {exc}",
                          console_only=console_only)
        return 1

    if args.status:
        print(f"HERCULE v{APP_VERSION}")
        for key, value in health.items():
            print(f"  {key:10s} {value}")
        return 0

    # Startup stage 4: first-run screen (skipped with --headless/--no-first-run)
    try:
        if not args.headless and not args.no_first_run and is_first_run():
            show_first_run_screen(health)
            mark_first_run_done()
    except Exception as exc:
        log.warning("first-run screen skipped: %s", exc)

    # Startup stage 5: main loop
    worker = None
    try:
        if isinstance(services, dict):
            worker = services.get("autonomy_worker")
        if args.headless:
            return run_headless(services)
        try:
            return run_gui(services)
        except Exception as exc:
            show_error_dialog("desktop-ui", "ui", f"desktop UI unavailable: {exc}")
            print("Falling back to headless console.\n")
            return run_headless(services)
    finally:
        try:
            if worker is not None:
                worker.stop()
        except Exception:
            pass
        try:
            brain = services.get("brain") if isinstance(services, dict) else None
            if brain is not None and hasattr(brain, "shutdown"):
                brain.shutdown()
        except Exception:
            pass
        log.info("HERCULE shutdown complete")


if __name__ == "__main__":
    raise SystemExit(main())
