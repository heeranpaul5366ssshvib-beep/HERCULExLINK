from __future__ import annotations
"""Local-to-Kaggle GPU training controller (orchestrator only).

LOCAL PC prepares, submits, monitors, retrieves, evaluates.
KAGGLE GPU does the expensive training. Never the reverse.
"""

from tools.kaggle_trainer.controller import train_remote

__all__ = ["train_remote"]
