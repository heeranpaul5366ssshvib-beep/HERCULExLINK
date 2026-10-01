from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Calculator Ability
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abilities.base_ability import BaseAbility

import ast
import operator as _operator
import re as _re


_SAFE_OPERATORS = {
    ast.Add: _operator.add, ast.Sub: _operator.sub, ast.Mult: _operator.mul,
    ast.Div: _operator.truediv, ast.FloorDiv: _operator.floordiv,
    ast.Mod: _operator.mod, ast.Pow: _operator.pow, ast.USub: _operator.neg,
    ast.UAdd: _operator.pos,
}


# Spoken/natural operator words accepted by the evaluator (v1.1 voice:
# transcripts say "times"/"plus", not "*"/"+"). Whole-word matches only,
# applied before parsing; the strict AST gate below still rejects
# anything that is not plain arithmetic, so this can only turn honest
# failures into successes, never unsafe input into execution.
_WORD_OPERATORS = (
    ("multiplied by", "*"),
    ("divided by", "/"),
    ("to the power of", "**"),
    ("plus", "+"),
    ("minus", "-"),
    ("times", "*"),
    ("over", "/"),
)


def normalize_spoken_arithmetic(expression: str) -> str:
    """Map natural operator words/punctuation to evaluable symbols."""
    text = str(expression or "")
    for words, symbol in _WORD_OPERATORS:
        pattern = r"(?i)\b" + r"\s+".join(words.split()) + r"\b"
        text = _re.sub(pattern, f" {symbol} ", text)
    text = _re.sub(r"(?<=\d),(?=\d)", "", text)  # thousand separators
    text = text.strip()
    text = _re.sub(r"[?!;]+$", "", text).strip()
    text = _re.sub(r"\.(?!\d)$", "", text)  # trailing sentence dot, not decimals
    return text.strip()


def safe_evaluate(expression: str):
    """Evaluate arithmetic only (numbers + - * / // % ** and parens)."""
    node = ast.parse(normalize_spoken_arithmetic(expression), mode="eval")

    def _eval(n):
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _SAFE_OPERATORS:
            return _SAFE_OPERATORS[type(n.op)](_eval(n.left), _eval(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _SAFE_OPERATORS:
            return _SAFE_OPERATORS[type(n.op)](_eval(n.operand))
        raise ValueError(f"unsupported expression element: {type(n).__name__}")

    return _eval(node)


class CalculatorAbility(BaseAbility):

    def __init__(self):

        super().__init__(
            "calculator",
            "Arithmetic calculator",
            capability="MATH",
            inputs={"expression": "arithmetic string, e.g. '25 * 4'"},
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
        if _re.search(r"[a-zA-Z_]{2,}", text):
            return "only arithmetic expressions are allowed"
        return ""

    def execute(
        self,
        task,
        context=None,
        **kwargs,
    ):
        expression = str(task if task is not None else kwargs.get("expression", ""))
        # Accept natural phrasing: "calculate 25 * 4" -> "25 * 4".
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