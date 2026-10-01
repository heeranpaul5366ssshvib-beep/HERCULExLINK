from memory.vector.vector_manager import VectorMemory
from models.adapters.mock_adapter import MockAdapter


def test_vector_store_and_search():
    vm = VectorMemory()
    adapter = MockAdapter(dim=64)

    docs = [
        "HERCULE stores memories as vectors.",
        "Agents execute tasks and write to memory.",
        "The orchestrator coordinates subsystems.",
    ]

    for d in docs:
        vm.add(d, adapter._text_to_vector(d), metadata={"source": "test"})

    q = adapter._text_to_vector("How does memory store vectors?")
    res = vm.search(q, top_k=2)

    assert isinstance(res, list)
    assert len(res) >= 1
    # top result should be a dict containing text and score
    top = res[0]
    assert "text" in top
    assert "score" in top
