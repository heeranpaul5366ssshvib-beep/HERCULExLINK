from __future__ import annotations
"""Render Mermaid diagrams using the Mermaid CLI (`mmdc`).

Usage:
  python tools/render_mermaid.py docs/architecture_diagram.mmd docs/architecture_diagram.svg

This script simply wraps `mmdc` if available and provides a friendly message otherwise.
"""
import shutil
import subprocess
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: python tools/render_mermaid.py <input.mmd> <output.svg>")
        return 2
    in_file = argv[1]
    out_file = argv[2]

    if shutil.which("mmdc") is None:
        print("Error: `mmdc` (Mermaid CLI) not found. Install with: npm install -g @mermaid-js/mermaid-cli")
        return 3

    cmd = ["mmdc", "-i", in_file, "-o", out_file]
    try:
        subprocess.run(cmd, check=True)
        print(f"Rendered {out_file}")
        return 0
    except subprocess.CalledProcessError as e:
        print("mmdc failed:", e)
        return 4


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
