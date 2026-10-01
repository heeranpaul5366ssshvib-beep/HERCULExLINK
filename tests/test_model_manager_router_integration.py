from models.model_manager import ModelManager


def test_model_manager_router_routes_and_falls_back():
    manager = ModelManager(default_model="llama3")
    # should still work with default path, but router is now active
    response = manager.generate("Summarize the status of the local model router.")
    assert isinstance(response, str)
    assert len(response) > 0


def test_model_manager_explicit_selection_keeps_compatibility():
    manager = ModelManager(default_model="llama3")
    manager.load_model("mock")
    response = manager.generate("Run a simple test prompt.")
    assert "MOCK ANSWER" in response
