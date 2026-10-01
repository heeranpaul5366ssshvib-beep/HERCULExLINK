from memory.memory_manager import MemoryManager


def test_memory_creation():

    memory = MemoryManager()

    assert memory is not None