from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Retrieval Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from typing import Any


class RetrievalEngine:

    def __init__(self):

        self._sources: dict[str, Any] = {}

    def register_source(
        self,
        name: str,
        source: Any,
    ):

        self._sources[name] = source

    def unregister_source(
        self,
        name: str,
    ):

        self._sources.pop(name, None)

    def source(
        self,
        name: str,
    ):

        return self._sources.get(name)

    def search(
        self,
        query: str,
    ):

        results = {}

        for name, source in self._sources.items():

            if hasattr(source, "search"):

                try:

                    results[name] = source.search(query)

                except Exception:

                    continue

        return results

    def sources(self):

        return list(self._sources.keys())