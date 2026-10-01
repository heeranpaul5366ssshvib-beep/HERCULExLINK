from brain.brain import Brain


class DummyAgent:

    def think(self, prompt):

        return prompt


class DummyOrchestrator:

    def __init__(self):

        self.agent = DummyAgent()

    def execute(self, *args, **kwargs):

        return True

    def health(self):

        return {}


def test_brain_creation():

    brain = Brain(

        DummyOrchestrator(),

    )

    assert brain is not None


def test_brain_start():

    brain = Brain(

        DummyOrchestrator(),

    )

    brain.start()

    assert brain.running


def test_brain_stop():

    brain = Brain(

        DummyOrchestrator(),

    )

    brain.start()

    brain.stop()

    assert not brain.running