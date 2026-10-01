from __future__ import annotations
"""Write RELEASE_MANIFEST.json for the v1.0 production release.

Reads the authoritative version, hashes the built artifacts, and
records runtime/packaging requirements. No secrets are included.
Run AFTER scripts/build_exe.py and scripts/build_installer.py.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(rel: str):
    path = REPO / rel
    if not path.exists():
        return {"path": rel, "present": False}
    return {"path": rel, "present": True,
            "bytes": path.stat().st_size,
            "sha256": sha256(path)}


def pyinstaller_version() -> str:
    try:
        import PyInstaller
        return str(getattr(PyInstaller, "__version__", "unknown"))
    except Exception:
        return "not installed"


def main() -> int:
    from system.version import APP_FULL_NAME, APP_NAME, __version__

    exe = artifact("dist/HERCULE/HERCULE.exe")
    setup = artifact("installer-output/HERCULE-Setup.exe")
    manifest = {
        "application": APP_NAME,
        "full_name": APP_FULL_NAME,
        "version": __version__,
        "build_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "python_required": ">=3.11 (built with 3.14.6)",
        "runtime_requirements": [
            "Windows 10/11 x64",
            "Ollama running locally (default http://127.0.0.1:11434)",
            "At least one Ollama chat model installed (e.g. ollama pull llama3.2:3b)",
            "No API keys required for the local Ollama path",
        ],
        "packaging": {"tool": "PyInstaller", "version": pyinstaller_version(),
                      "mode": "onedir", "installer": "Inno Setup 6"},
        "components": ["Brain", "Consciousness", "MemoryManager", "ModelManager",
                       "AbilityManager", "Planner", "CapabilityRegistry",
                       "ToolMatcher", "PolicyManager", "AutonomousLoop",
                       "TaskManager", "ExperienceManager", "AutonomyWorker",
                       "Desktop UI (tkinter)", "HUD overlay", "CLI/headless",
                       "Health report + /health diagnostics"],
        "artifacts": {"executable": exe, "installer": setup},
        "excluded_from_package": [".venv", "tests", "development caches",
                                  "temporary data", "local task state",
                                  "local memory databases", "model weights",
                                  "secrets"],
        "user_data_location": "%LOCALAPPDATA%\\HERCULE (preserved on upgrade/uninstall)",
    }
    if not exe.get("present") or not setup.get("present"):
        print("missing artifacts: build exe + installer first")
        return 1
    out = REPO / "RELEASE_MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
