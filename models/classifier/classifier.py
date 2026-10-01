from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Task Classifier
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class TaskClassifier:

    TASKS = {

        "coding": [
            "code",
            "python",
            "java",
            "bug",
            "debug",
            "program",
            "algorithm",
        ],

        "research": [
            "research",
            "study",
            "paper",
            "analyse",
            "analysis",
            "compare",
            "investigate",
        ],

        "engineering": [
            "engine",
            "cad",
            "mechanical",
            "electrical",
            "robot",
            "physics",
        ],

        "mathematics": [
            "solve",
            "equation",
            "math",
            "calculate",
            "matrix",
            "integral",
        ],

        "documents": [
            "pdf",
            "doc",
            "document",
            "word",
            "excel",
        ],

        "conversation": [
            "hello",
            "hi",
            "thanks",
            "who are you",
        ],
    }

    def classify(self, text: str) -> str:

        text = text.lower()

        scores = {}

        for task, keywords in self.TASKS.items():

            score = 0

            for word in keywords:

                if word in text:
                    score += 1

            scores[task] = score

        best = max(scores, key=scores.get)

        if scores[best] == 0:
            return "general"

        return best