from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Reasoner
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from models.model_manager import ModelManager


class Reasoner:
    """
    Performs reasoning using the Model System.
    """

    def __init__(

        self,

        model_manager: ModelManager,

    ):

        self.model_manager = model_manager

    def think(

        self,

        prompt: str,

        context: str = "",

    ) -> str:

        if context:

            prompt = f"{context}\n\n{prompt}"

        if self.model_manager is None:
            return f"Reasoned about: {prompt}"

        if hasattr(self.model_manager, "generate"):
            # Internal reasoning only needs a concise summary (traces keep
            # ~200 chars ≈ 48 tokens); cap tokens to bound latency.
            try:
                return self.model_manager.generate(
                    prompt, options={"num_predict": 48})
            except TypeError:
                return self.model_manager.generate(prompt)

        if hasattr(self.model_manager, "chat"):
            return self.model_manager.chat(prompt)

        return f"Reasoned about: {prompt}"

    def explain(

        self,

        topic: str,

    ):

        return self.think(

            f"Explain the following clearly:\n\n{topic}"

        )

    def solve(

        self,

        problem: str,

    ):

        return self.think(

            f"Solve this problem step by step:\n\n{problem}"

        )