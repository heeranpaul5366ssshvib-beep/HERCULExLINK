from system.system_manager import SystemManager


def test_system_creation():

    system = SystemManager()

    assert system is not None


def test_system_initialize():

    system = SystemManager()

    system.initialize()

    assert True