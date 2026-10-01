from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Base Adapter
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abc import ABC, abstractmethod


class BaseAdapter(ABC):

    def health(self):
        return {"status": "healthy", "available": True}

    @abstractmethod
    def chat(
        self,
        model: str,
        prompt: str,
        system: str = "",
    ):
        ...

    @abstractmethod
    def embeddings(
        self,
        model: str,
        text: str,
    ):
        ...