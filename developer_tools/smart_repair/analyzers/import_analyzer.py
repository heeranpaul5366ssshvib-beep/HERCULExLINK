from __future__ import annotations
"""
HERCULE Smart Repair Engine

Import Analyzer

Scans Python files for import-related issues.
"""


import ast
import importlib.util
from pathlib import Path
from typing import Dict, List


class ImportAnalyzer:
    """
    Detects broken, duplicate and suspicious imports.

    This analyzer NEVER modifies code.
    """

    def scan(self, file_path: Path) -> List[Dict]:

        issues = []

        file_path = Path(file_path)

        try:

            source = file_path.read_text(
                encoding="utf-8"
            )

        except Exception as exc:

            return [{
                "type": "read_error",
                "severity": "CRITICAL",
                "message": str(exc),
                "file": str(file_path)
            }]

        try:

            tree = ast.parse(source)

        except SyntaxError:

            return [{
                "type": "syntax_error",
                "severity": "CRITICAL",
                "file": str(file_path)
            }]

        imports = []
        seen = set()

        for node in ast.walk(tree):

            # ---------------- Imports ----------------

            if isinstance(node, ast.Import):

                for alias in node.names:

                    imports.append(alias.name)

                    if alias.name in seen:

                        issues.append({

                            "type": "duplicate_import",

                            "severity": "LOW",

                            "module": alias.name,

                            "line": node.lineno

                        })

                    seen.add(alias.name)

            # ---------------- From Imports ----------------

            elif isinstance(node, ast.ImportFrom):

                module = node.module or ""

                imports.append(module)

                if module in seen:

                    issues.append({

                        "type": "duplicate_import",

                        "severity": "LOW",

                        "module": module,

                        "line": node.lineno

                    })

                seen.add(module)

        # --------------------------------------------------

        for module in imports:

            if not module:

                continue

            try:

                found = importlib.util.find_spec(module)

            except Exception:

                found = None

            if found is None:

                issues.append({

                    "type": "missing_import",

                    "severity": "HIGH",

                    "module": module,

                    "file": str(file_path)

                })

        return issues