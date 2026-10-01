from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Agent
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class Agent:
    """
    ==========================================
             HERCULE AGENT
    ==========================================

    AI decision making entity.
    """

    def __init__(

        self,

        memory,

        knowledge,

        models,

        abilities,

    ):

        self.memory = memory

        self.knowledge = knowledge

        self.models = models

        self.abilities = abilities

        self.goal = None

        self.context = {}

    ##################################################

    def set_goal(

        self,

        goal,

    ):

        self.goal = goal

    ##################################################

    def get_goal(self):

        return self.goal

    ##################################################

    def remember(

        self,

        key,

        value,

    ):

        self.context[key] = value

    ##################################################

    def recall(

        self,

        key,

    ):

        return self.context.get(

            key,

        )

    ##################################################

    def think(

        self,

        prompt,

        system=None,

        context="",

        memory="",

        model=None,

        options=None,

    ):
        """Reason/converse via the model with system prompt + bounded context.

        USER REQUEST → MEMORY RETRIEVAL → CONTEXT → LLM → RESPONSE.
        Only caller-supplied relevant context is sent (never the whole
        memory database). The model reasons/proposes; it never executes.
        ``model``/``options`` carry the adaptive reasoning budget
        (additive; None preserves legacy routing exactly).
        """
        from models.prompts.prompt_manager import PromptManager

        manager = getattr(self, "prompt_manager", None)
        if manager is None:
            manager = PromptManager()
            self.prompt_manager = manager
        built = manager.build(str(prompt), context=str(context or ""),
                              memory=str(memory or "")[:500])
        call_kwargs: dict = {}
        if model:
            call_kwargs["model"] = model
        if options:
            call_kwargs["options"] = dict(options)
        return self.models.generate(
            built,
            system=system if system is not None else manager.get_system_prompt(),
            **call_kwargs,
        )

    ##################################################

    def execute_ability(

        self,

        ability,

        *args,

        **kwargs,

    ):

        return self.abilities.execute(

            ability,

            *args,

            **kwargs,

        )

    ##################################################

    def reset(self):

        self.goal = None

        self.context.clear()
