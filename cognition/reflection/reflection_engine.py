from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Reflection Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class ReflectionEngine:
    """
    Reviews previous reasoning.
    """

    def reflect(
        self,
        prompt: str,
        answer: str,
    ):

        return {

            "prompt": prompt,

            "answer": answer,

            "improved": False,

            "notes": [],

        }

    def improve(
        self,
        reflection: dict,
        notes: str,
    ):

        reflection["notes"].append(notes)

        reflection["improved"] = True

        return reflection