from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin API
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class PluginAPI:

    """
    Safe interface exposed to plugins.

    Plugins interact with HERCULE only
    through this class.
    """

    def __init__(

        self,

        brain,

        orchestrator,

        memory,

        knowledge,

        models,

        abilities,

        communication,

        perception,

        security,

        system,

    ):

        self.brain = brain

        self.orchestrator = orchestrator

        self.memory = memory

        self.knowledge = knowledge

        self.models = models

        self.abilities = abilities

        self.communication = communication

        self.perception = perception

        self.security = security

        self.system = system

    ##################################################
    # MEMORY
    ##################################################

    def remember(

        self,

        key,

        value,

    ):

        return self.memory.store(

            key,

            value,

        )

    ##################################################

    def recall(

        self,

        key,

    ):

        return self.memory.retrieve(

            key,

        )

    ##################################################
    # MODELS
    ##################################################

    def generate(

        self,

        prompt,

    ):

        return self.models.generate(

            prompt,

        )

    ##################################################
    # ABILITIES
    ##################################################

    def ability(

        self,

        name,

        *args,

        **kwargs,

    ):

        return self.abilities.execute(

            name,

            *args,

            **kwargs,

        )

    ##################################################
    # KNOWLEDGE
    ##################################################

    def search(

        self,

        query,

    ):

        return self.knowledge.search(

            query,

        )

    ##################################################
    # BRAIN
    ##################################################

    def think(

        self,

        prompt,

    ):

        return self.brain.think(

            prompt,

        )

    ##################################################
    # SYSTEM
    ##################################################

    def status(self):

        return self.system.status()

    ##################################################

    def health(self):

        return self.orchestrator.health()