from orchestrator.orchestrator import Orchestrator


def test_orchestrator_creation():

    orchestrator = Orchestrator(

        memory=None,

        knowledge=None,

        models=None,

        abilities=None,

        perception=None,

        communication=None,

        security=None,

        system=None,

    )

    assert orchestrator is not None