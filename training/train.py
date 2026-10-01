from __future__ import annotations
"""Shim: python -m training.train -> models.hercule_lm.train."""
import sys

from models.hercule_lm.train import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
