from __future__ import annotations
"""Shim: python -m training.evaluate -> models.hercule_lm.evaluate."""
import sys

from models.hercule_lm.evaluate import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
