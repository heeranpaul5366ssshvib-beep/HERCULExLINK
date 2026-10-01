from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Tokenizer
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class Tokenizer:

    """
    Placeholder tokenizer.

    Can later be replaced with
    tiktoken, llama tokenizer,
    sentencepiece, etc.
    """

    def count(self, text: str) -> int:

        return len(text.split())

    def estimate_remaining(
        self,
        text: str,
        context_limit: int,
    ) -> int:

        return max(
            context_limit - self.count(text),
            0,
        )