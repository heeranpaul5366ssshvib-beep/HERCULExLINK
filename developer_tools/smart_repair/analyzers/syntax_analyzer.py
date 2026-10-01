from __future__ import annotations
"""
HERCULE Smart Repair Engine

Syntax Analyzer

Detects Python syntax problems before runtime.
"""


import ast
import tokenize
from pathlib import Path
from typing import Dict, List


class SyntaxAnalyzer:
    """
    Detects syntax and formatting issues.

    Read-only analyzer.
    """

    def scan(self, file_path: Path) -> List[Dict]:

        issues: List[Dict] = []

        file_path = Path(file_path)

        if not file_path.exists():

            return [{
                "type": "missing_file",
                "severity": "CRITICAL",
                "file": str(file_path)
            }]

        # -------------------------------------
        # Read source
        # -------------------------------------

        try:

            source = file_path.read_text(
                encoding="utf-8"
            )

        except UnicodeDecodeError:

            return [{
                "type": "encoding_error",
                "severity": "CRITICAL",
                "file": str(file_path)
            }]

        except Exception as exc:

            return [{
                "type": "read_error",
                "severity": "CRITICAL",
                "message": str(exc),
                "file": str(file_path)
            }]

        # -------------------------------------
        # __future__ position
        # -------------------------------------

        future_line = None

        for index, line in enumerate(source.splitlines(), start=1):

            stripped = line.strip()

            if not stripped:

                continue

            if stripped.startswith("#"):

                continue


                future_line = index

            break

        if future_line and future_line != 1:

            issues.append({

                "type": "future_import_position",

                "severity": "HIGH",

                "line": future_line,

                "message":
                    "__future__ import should be first statement."

            })

        # -------------------------------------
        # AST validation
        # -------------------------------------

        try:

            ast.parse(source)

        except SyntaxError as exc:

            issues.append({

                "type": "syntax_error",

                "severity": "CRITICAL",

                "line": exc.lineno,

                "column": exc.offset,

                "message": exc.msg

            })

        # -------------------------------------
        # Tokenization
        # -------------------------------------

        try:

            with open(file_path, "rb") as f:

                list(tokenize.tokenize(f.readline))

        except tokenize.TokenError as exc:

            issues.append({

                "type": "token_error",

                "severity": "HIGH",

                "message": str(exc)

            })

        # -------------------------------------
        # Mixed tabs/spaces
        # -------------------------------------

        has_tabs = False
        has_spaces = False

        for line in source.splitlines():

            if line.startswith("\t"):

                has_tabs = True

            elif line.startswith(" "):

                has_spaces = True

        if has_tabs and has_spaces:

            issues.append({

                "type": "mixed_indentation",

                "severity": "MEDIUM",

                "message":
                    "Tabs and spaces are mixed."

            })

        return issues