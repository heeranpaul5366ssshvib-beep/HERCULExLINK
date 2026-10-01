from __future__ import annotations
"""
--------------------------------------------
HERCULE Boot Loader
--------------------------------------------
"""


from runtime.runtime import Runtime
from boot.environment import Environment
from boot.diagnostics import Diagnostics
from boot.startup import Startup
from boot.shutdown import Shutdown


class BootLoader:

    def __init__(self):

        self.environment = Environment()

        self.runtime = Runtime()

        self.diagnostics = Diagnostics()

        self.startup = Startup()

        self.shutdown = Shutdown()

    ##################################################

    def boot(self):

        self.runtime.boot()

        self.startup.execute(

            self.runtime,

        )

        return True

    ##################################################

    def stop(self):

        self.shutdown.execute(

            self.runtime,

        )

    ##################################################

    def health(self):

        return self.diagnostics.run(

            self.runtime.registry,

        )

    ##################################################

    def environment_info(self):

        return self.environment.get()