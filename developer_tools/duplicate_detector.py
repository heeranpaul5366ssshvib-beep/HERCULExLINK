from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Duplicate Detector

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import hashlib
from pathlib import Path
from typing import Dict, List


class DuplicateDetector:
    """
    Detects duplicate files within the
    HERCULE project.

    Checks:

    • Duplicate files
    • Duplicate file contents
    • Duplicate hashes
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def scan(self) -> Dict:

        hashes: Dict[str, List[str]] = {}

        for file in self.project_root.rglob("*"):

            if not file.is_file():

                continue

            try:

                digest = self._hash(file)

                relative = str(

                    file.relative_to(
                        self.project_root
                    )

                )

                hashes.setdefault(

                    digest,

                    []

                ).append(relative)

            except Exception:

                continue

        duplicates = []

        for digest, files in hashes.items():

            if len(files) > 1:

                duplicates.append({

                    "hash": digest,

                    "files": files,

                    "count": len(files),

                })

        return {

            "files_scanned": sum(

                len(v)

                for v in hashes.values()

            ),

            "duplicate_groups":

                len(duplicates),

            "duplicates":

                duplicates,

        }

    # --------------------------------------------------

    def _hash(
        self,
        file: Path,
    ) -> str:

        hasher = hashlib.sha256()

        with open(

            file,

            "rb",

        ) as stream:

            while True:

                chunk = stream.read(

                    8192

                )

                if not chunk:

                    break

                hasher.update(chunk)

        return hasher.hexdigest()

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.scan()

        print("\n========== Duplicate Detector ==========\n")

        print(

            f"Files Scanned    : "

            f"{report['files_scanned']}"

        )

        print(

            f"Duplicate Groups : "

            f"{report['duplicate_groups']}"

        )

        if report["duplicates"]:

            print("\nDuplicates:\n")

            for group in report["duplicates"]:

                print(

                    f"Copies : "

                    f"{group['count']}"

                )

                for file in group["files"]:

                    print(

                        f"   {file}"

                    )

                print()

        else:

            print(

                "\nNo duplicate files found."

            )

        print(

            "\n========================================\n"

        )