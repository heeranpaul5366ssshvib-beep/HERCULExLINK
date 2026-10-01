from models.model_manager import ModelManager


def test_model_manager_creation():

    manager = ModelManager()

    assert manager is not None