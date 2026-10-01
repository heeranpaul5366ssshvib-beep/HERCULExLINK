"""``hercule`` namespace shim.

The canonical package root of the project is the repository itself;
``python -m hercule.evaluation`` addresses the evaluation CLI through
this thin namespace so the documented command works from the repo root
without renaming any frozen module.
"""
