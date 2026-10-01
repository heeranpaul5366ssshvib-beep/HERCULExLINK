from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Storage Manager
--------------------------------------------
"""


from pathlib import Path
import shutil


class StorageManager:

    ##################################################

    def exists(

        self,

        path,

    ):

        return Path(path).exists()

    ##################################################

    def create_directory(

        self,

        path,

    ):

        Path(path).mkdir(

            parents=True,

            exist_ok=True,

        )

    ##################################################

    def delete(

        self,

        path,

    ):

        path = Path(path)

        if path.is_dir():

            shutil.rmtree(path)

        elif path.exists():

            path.unlink()

    ##################################################

    def size(

        self,

        path,

    ):

        path = Path(path)

        if path.exists():

            return path.stat().st_size

        return 0