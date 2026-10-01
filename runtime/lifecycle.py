from __future__ import annotations
"""
--------------------------------------------
Runtime Lifecycle
--------------------------------------------
"""



class RuntimeLifecycle:

    def __init__(self):

        self.running = False

    ##################################################

    def start(self):

        self.running = True

    ##################################################

    def stop(self):

        self.running = False

    ##################################################

    def restart(self):

        self.stop()

        self.start()