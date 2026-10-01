"""Demo: simple RAG flow using in-memory vector store and mock adapter.

Run as: python -m examples.demo_rag
"""
from memory.vector.vector_manager import VectorMemory
from models.adapters.mock_adapter import MockAdapter


def run_demo():
    vm = VectorMemory()
    adapter = MockAdapter(dim=64)

    docs = [
        "HERCULE is an AI operating system for local LLMs.",
        "The memory subsystem stores vector embeddings for retrieval.",
        "Agents coordinate tools and perform tasks on behalf of users.",
    ]

    vectors = adapter.embeddings(docs)
    for d, v in zip(docs, vectors):
        vm.add(d, v, metadata={"source": "demo"})

    question = "How does memory work in HERCULE?"
    qvec = adapter.embeddings([question])[0]
    results = vm.search(qvec, top_k=2)

    retrieved = [r["text"] if isinstance(r, dict) else r.get("text") for r in results]
    # model prompt
    prompt = f"Answer the question concisely: {question}\nUse the following context:\n" + "\n".join(retrieved)
    answer = adapter.chat(prompt, context=retrieved)
    print("Retrieved:")
    for r in results:
        print(f"- score={r.get('score'):.3f} text={r.get('text')}")
    print("\nAnswer:\n", answer)
    return answer


if __name__ == "__main__":
    run_demo()
