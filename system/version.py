from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Authoritative Application Version
--------------------------------------------

Single source of truth for the HERCULE application version.
Keep in sync with:
  * pyproject.toml [project] version  (packaging metadata)
  * installer/hercule.iss MyAppVersion (Inno Setup cannot import Python)
  * assets/installer filenames in release docs
"""

__version__ = "1.1.0"
APP_NAME = "HERCULE"
APP_FULL_NAME = "HERCULE AI Operating System"
