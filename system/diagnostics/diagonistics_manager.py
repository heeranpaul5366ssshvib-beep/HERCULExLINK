from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Diagnostics Manager
--------------------------------------------
"""


from datetime import datetime


class DiagnosticsManager:

    def __init__(self):

        self.reports = []

    ##################################################

    def run(self):

        report = {

            "timestamp": datetime.now(),

            "status": "OK",

            "errors": [],

            "warnings": [],

        }

        self.reports.append(report)

        return report

    ##################################################

    def history(self):

        return self.reports

    ##################################################

    def latest(self):

        if not self.reports:

            return None

        return self.reports[-1]