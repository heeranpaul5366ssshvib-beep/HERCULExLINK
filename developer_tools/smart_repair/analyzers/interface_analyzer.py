from __future__ import annotations
"""
HERCULE Smart Repair Engine

Interface Analyzer

Detects interface and API mismatches.
"""


import ast
from pathlib import Path
from typing import Dict, List


class InterfaceAnalyzer:
    """
    Analyzes classes, methods and calls
    for interface inconsistencies.

    Read-only.
    """

    def scan(self, file_path: Path) -> List[Dict]:

        issues = []

        file_path = Path(file_path)

        try:

            source = file_path.read_text(
                encoding="utf-8"
            )

            tree = ast.parse(source)

        except Exception as exc:

            return [

                {
                    "type": "parse_error",
                    "severity": "CRITICAL",
                    "message": str(exc),
                    "file": str(file_path),
                }

            ]

        classes = {}

        # -------------------------
        # Collect classes/methods
        # -------------------------

        for node in ast.walk(tree):

            if isinstance(node, ast.ClassDef):

                methods = {}

                for item in node.body:

                    if isinstance(item, ast.FunctionDef):

                        methods[item.name] = len(item.args.args)

                classes[node.name] = methods

        # -------------------------
        # Detect duplicate methods
        # -------------------------

        for cls, methods in classes.items():

            duplicates = {}

            for method in methods:

                duplicates[method] = duplicates.get(method, 0) + 1

            for method, count in duplicates.items():

                if count > 1:

                    issues.append({

                        "type": "duplicate_method",

                        "severity": "HIGH",

                        "class": cls,

                        "method": method,

                    })

        # -------------------------
        # Detect calls
        # -------------------------

        for node in ast.walk(tree):

            if isinstance(node, ast.Call):

                if isinstance(node.func, ast.Attribute):

                    issues.append({

                        "type": "method_call",

                        "severity": "INFO",

                        "method": node.func.attr,

                        "line": node.lineno,

                        "arguments":

                            len(node.args)

                            + len(node.keywords),

                    })

        # -------------------------
        # Empty classes
        # -------------------------

        for cls, methods in classes.items():

            if len(methods) == 0:

                issues.append({

                    "type": "empty_class",

                    "severity": "MEDIUM",

                    "class": cls,

                })

        return issues   