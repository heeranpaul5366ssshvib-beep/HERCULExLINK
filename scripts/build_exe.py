"""Reproducible HERCULE executable build (PyInstaller --onedir)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except Exception:
        print("PyInstaller not found, installing...")
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])
        if rc != 0:
            print("pip install pyinstaller failed")
            return rc
    # Clean previous bundle output (never user data).
    for stale in (REPO / "build", REPO / "dist"):
        if stale.exists():
            shutil.rmtree(stale, ignore_errors=True)
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "hercule.spec"]
    print("+", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(REPO))
    if rc != 0:
        return rc
    exe = REPO / "dist" / "HERCULE" / "HERCULE.exe"
    print(f"build complete: {exe} (exists={exe.exists()})")
    return 0 if exe.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
