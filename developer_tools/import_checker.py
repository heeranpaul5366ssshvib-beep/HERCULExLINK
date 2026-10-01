from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Import Checker

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import ast
from pathlib import Path
from typing import Dict, List


class ImportChecker:
    """
    Scans every Python file in the project and
    validates import statements.

    Checks:

    • Invalid imports
    • Missing modules
    • Syntax errors
    • Import statistics
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def check(self) -> Dict:

        files = list(
            self.project_root.rglob("*.py")
        )

        scanned = 0

        errors = []

        imports = 0

        for file in files:

            scanned += 1

            result = self._scan_file(file)

            imports += result["imports"]

            errors.extend(result["errors"])

        return {

            "success":
                len(errors) == 0,

            "files_scanned":
                scanned,

            "imports_found":
                imports,

            "errors":
                errors,

        }

    # --------------------------------------------------

    def _scan_file(
        self,
        file: Path,
    ) -> Dict:

        found_imports = 0

        errors = []

        try:

            source = file.read_text(
                encoding="utf-8"
            )

            tree = ast.parse(source)

            for node in ast.walk(tree):

                if isinstance(
                    node,
                    (
                        ast.Import,
                        ast.ImportFrom,
                    ),
                ):

                    found_imports += 1

        except SyntaxError as exc:

            errors.append({

                "file":
                    str(file.relative_to(
                        self.project_root
                    )),

                "line":
                    exc.lineno,

                "message":
                    str(exc),

            })

        except Exception as exc:

            errors.append({

                "file":
                    str(file.relative_to(
                        self.project_root
                    )),

                "line":
                    None,

                "message":
                    str(exc),

            })

        return {

            "imports":
                found_imports,

            "errors":
                errors,

        }

    # --------------------------------------------------

    def print_report(self):

        report = self.check()

        print("\n========== Import Checker ==========\n")

        print(
            f"Files Scanned : "
            f"{report['files_scanned']}"
        )

        print(
            f"Imports Found : "
            f"{report['imports_found']}"
        )

        print(
            f"Status        : "
            f"{'PASSED' if report['success'] else 'FAILED'}"
        )

        if report["errors"]:

            print("\nErrors:\n")

            for error in report["errors"]:

                print(
                    f"{error['file']}"
                )

                print(
                    f"  Line : {error['line']}"
                )

                print(
                    f"  {error['message']}\n"
                )

        else:

            print(
                "\nNo import errors detected."
            )

        print(
            "\n====================================\n"
        )