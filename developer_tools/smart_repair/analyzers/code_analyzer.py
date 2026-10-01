from __future__ import annotations
"""
HERCULE Smart Repair Engine

Generic Python Code Analyzer
"""


import ast
from pathlib import Path
from typing import Dict, List


class CodeAnalyzer:
    """
    Performs a structural analysis of Python files.

    This analyzer does not repair anything.
    It only reports findings.
    """

    def scan(self, file_path: Path) -> List[Dict]:

        issues = []

        file_path = Path(file_path)

        if not file_path.exists():

            issues.append({

                "type": "missing_file",

                "severity": "CRITICAL",

                "message": "File does not exist.",

                "file": str(file_path)

            })

            return issues

        try:

            source = file_path.read_text(
                encoding="utf-8"
            )

        except Exception as exc:

            issues.append({

                "type": "read_error",

                "severity": "CRITICAL",

                "message": str(exc),

                "file": str(file_path)

            })

            return issues

        try:

            tree = ast.parse(source)

        except SyntaxError as exc:

            issues.append({

                "type": "syntax_error",

                "severity": "CRITICAL",

                "line": exc.lineno,

                "message": exc.msg,

                "file": str(file_path)

            })

            return issues

        classes = []

        functions = []

        imports = []

        for node in ast.walk(tree):

            if isinstance(node, ast.ClassDef):

                classes.append(node.name)

            elif isinstance(node, ast.FunctionDef):

                functions.append(node.name)

            elif isinstance(node, ast.Import):

                for alias in node.names:

                    imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):

                module = node.module or ""

                imports.append(module)

        return [

            {

                "type": "analysis",

                "severity": "INFO",

                "file": str(file_path),

                "classes": classes,

                "functions": functions,

                "imports": imports,

                "class_count": len(classes),

                "function_count": len(functions),

                "import_count": len(imports)

            }

        ]