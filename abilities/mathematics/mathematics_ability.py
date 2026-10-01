from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Mathematics Ability
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abilities.base_ability import BaseAbility

from abilities.calculator.calculator_ability import safe_evaluate

import re as _re


class MathematicsAbility(BaseAbility):

    def __init__(self):

        super().__init__(
            "mathematics",
            "Mathematical reasoning",
            capability="MATH",
            inputs={"expression": "arithmetic string"},
            outputs={"result": "number"},
            permissions=["MATH"],
            environments={"default"},
            verification="result verified by recomputation",
            timeout_s=10,
            risk="LOW",
        )

    ##################################################

    def validate_input(self, task, **kwargs):
        text = str(task if task is not None else kwargs.get("expression", ""))
        if not text.strip():
            return "empty expression"
        return ""

    def execute(
        self,
        task,
        context=None,
        **kwargs,
    ):
        expression = str(task if task is not None else kwargs.get("expression", ""))
        cleaned = _re.sub(r"(?i)^\s*(calculate|compute|solve|evaluate|what is|what's)\s*", "", expression).strip()
        try:
            result = safe_evaluate(cleaned)
            return {
                "status": "success",
                "expression": cleaned,
                "result": result,
            }
        except Exception as error:
            return {
                "status": "failed",
                "expression": cleaned,
                "error": str(error),
            } 