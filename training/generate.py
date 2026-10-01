from __future__ import annotations
"""Shim: python -m training.generate -> models.hercule_lm.generate."""
import sys

from models.hercule_lm.generate import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
