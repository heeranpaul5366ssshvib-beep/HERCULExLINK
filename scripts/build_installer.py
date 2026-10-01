from __future__ import annotations
"""Build HERCULE-Setup.exe from dist/HERCULE via Inno Setup (iscc).

Prefers `iscc` on PATH; otherwise tries the default install locations.
Reinstall/upgrade over an existing installation is supported by the
ISS script. User data (%LOCALAPPDATA%\\HERCULE) is never touched.
"""

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ISS = REPO / "installer" / "hercule.iss"
DIST = REPO / "dist" / "HERCULE" / "HERCULE.exe"


def find_iscc() -> str | None:
    found = shutil.which("iscc")
    if found:
        return found
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    local_programs = os.environ.get("LOCALAPPDATA", "")
    if local_programs:
        candidates.append(str(Path(local_programs) / "Programs" / "Inno Setup 6" / "ISCC.exe"))
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def main() -> int:
    if not DIST.exists():
        print(f"missing bundle: {DIST} — run: python scripts/build_exe.py")
        return 1
    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup (iscc) not found. Install Inno Setup 6, then re-run.")
        print("Download: https://jrsoftware.org/isdl.php")
        return 2
    cmd = [iscc, str(ISS)]
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(REPO / "installer"))


if __name__ == "__main__":
    raise SystemExit(main())
