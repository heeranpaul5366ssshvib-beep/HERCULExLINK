from __future__ import annotations
"""``python -m hercule.evaluation`` entry point.

Delegates to the framework CLI: quick/full evaluations, single-suite
runs, model comparison and regression baselines.
"""

import sys

from evaluation.framework.cli import main

if __name__ == "__main__":
    sys.exit(main())
