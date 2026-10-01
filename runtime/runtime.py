"""
--------------------------------------------
HERCULE AI Operating System
Runtime
--------------------------------------------
"""

from runtime.initializer import RuntimeInitializer

from runtime.lifecycle import RuntimeLifecycle

from runtime.validator import RuntimeValidator

from runtime.service_registry import ServiceRegistry

from runtime.dependency_graph import DependencyGraph


class Runtime:

    def __init__(self):

        self.registry = ServiceRegistry()

        self.graph = DependencyGraph()

        self.lifecycle = RuntimeLifecycle()

        self.validator = RuntimeValidator()

    ##################################################

    def initialize(self):

        initializer = RuntimeInitializer()

        services = initializer.initialize()

        for name, service in services.items():

            self.registry.register(

                name,

                service,

            )

        ##################################################
        # Dependency Graph
        ##################################################

        self.graph.add(

            "brain",

            [

                "memory",

                "knowledge",

                "models",

                "orchestrator",

            ],

        )

        self.graph.add(

            "orchestrator",

            [

                "abilities",

                "communication",

                "perception",

                "security",

                "system",

            ],

        )

    ##################################################

    def boot(self):

        self.initialize()

        report = self.validator.validate(

            self.registry,

        )

        if not report["valid"]:

            raise RuntimeError(

                report["missing"]

            )

        self.lifecycle.start()

        print("=" * 60)

        print("HERCULE AI Operating System")

        print("Runtime Started")

        print("=" * 60)

    ##################################################

    def shutdown(self):

        self.lifecycle.stop()

        print("Runtime Stopped")

    ##################################################

    def service(

        self,

        name,

    ):

        return self.registry.get(name)

    ##################################################

    def status(self):

        return {

            "running": self.lifecycle.running,

            "services": list(

                self.registry.all().keys()

            ),

        }