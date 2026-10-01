from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Learning Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class LearningEngine:

    """
    Executive learning controller.
    """

    def __init__(self):

        self.lessons = []

    ##################################################

    def learn(

        self,

        lesson,

    ):

        self.lessons.append(

            lesson,

        )

    ##################################################

    def knowledge(self):

        return self.lessons

    ##################################################

    def clear(self):

        self.lessons.clear()
