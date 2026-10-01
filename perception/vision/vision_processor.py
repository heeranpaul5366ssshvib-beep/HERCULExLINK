from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Vision Processor
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class VisionProcessor:

    def __init__(self):

        self.models = {}

    ##################################################

    def process(
        self,
        frame,
    ):

        return {

            "objects": [],

            "faces": [],

            "text": [],

            "frame": frame,

        }

    ##################################################

    def detect_objects(self, frame):

        return []

    ##################################################

    def detect_faces(self, frame):

        return []

    ##################################################

    def ocr(self, frame):

        return []