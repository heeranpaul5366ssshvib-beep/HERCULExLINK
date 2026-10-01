from __future__ import annotations
"""Explicit ethical frameworks (labels for analysis, not answers)."""

FRAMEWORKS = {
    "consequence": "weigh foreseeable outcomes for all stakeholders",
    "duty": "duties and rules that bind regardless of outcome",
    "fairness": "equal treatment and equitable distribution",
    "autonomy": "respect for informed consent and self-direction",
    "harm_minimization": "prefer the least harmful feasible option",
    "honesty": "do not deceive; preserve truthfulness",
    "privacy": "protect non-public personal information",
    "proportionality": "response must fit the stakes",
    "responsibility": "own foreseeable effects; keep auditability",
}

# Keyword cues mapping scenario text -> candidate principles (deterministic).
PRINCIPLE_CUES = {
    "harm_minimization": ("harm", "injure", "hurt", "kill", "damage", "risk"),
    "fairness": ("fair", "equal", "bias", "discriminat", "allocate", "share"),
    "privacy": ("private", "personal", "secret", "confidential", "data"),
    "autonomy": ("consent", "choice", "force", "coerce", "against their will"),
    "honesty": ("lie", "deceiv", "mislead", "truth", "honest"),
    "duty": ("duty", "obligation", "must", "rule", "promise"),
    "responsibility": ("responsib", "accountab", "blame", "audit"),
    "proportionality": ("proportion", "excessive", "minor", "stakes"),
    "consequence": ("outcome", "result", "effect", "benefit", "welfare"),
}
