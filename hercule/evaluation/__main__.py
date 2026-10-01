from __future__ import annotations
"""``python -m hercule.evaluation`` execution shim."""

import sys

from evaluation.framework.cli import main

if __name__ == "__main__":
    sys.exit(main())
