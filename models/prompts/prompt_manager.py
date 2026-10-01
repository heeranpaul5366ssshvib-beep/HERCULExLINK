from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Prompt Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class PromptManager:

    def __init__(self):

        self.system_prompt = (
            "You are HERCULE, an advanced AI Operating System. "
            "Be accurate, logical, safe, and concise. "
            "Identity: you are HERCULE, created for the HERCULE AI Operating "
            "System project. If asked your name, who you are, or who made "
            "you, answer as HERCULE. Never claim to be another company's "
            "model and never recite a pretrained vendor identity."
        )

    def build(
        self,
        user_prompt: str,
        context: str = "",
        memory: str = "",
    ) -> str:

        prompt = ""

        if context:
            prompt += f"Context:\n{context}\n\n"

        if memory:
            prompt += f"Memory:\n{memory}\n\n"

        prompt += f"User:\n{user_prompt}"

        return prompt

    def get_system_prompt(self) -> str:

        return self.system_prompt

    def set_system_prompt(self, prompt: str):

        self.system_prompt = prompt