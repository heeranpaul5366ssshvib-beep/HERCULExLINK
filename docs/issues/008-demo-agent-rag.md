# Issue 008 — Demo Agent: RAG (Memory + LLM)

Priority: High
Estimate: 1–2 person-weeks

Goal
- Build a minimal demo agent that answers questions using retrieval-augmented generation (RAG) with the new vector store and model adapter.

Acceptance criteria
- A runnable demo script that: indexes sample documents into the vector store, accepts a question, retrieves context, calls the model adapter, and returns an answer.
- Automated test verifying end-to-end flow with mocked model adapter.

Files to change (suggested)
- `examples/demo_rag.py` — demo script
- `agents/` — add a simple `demo_agent` or reuse `agent_manager` to run the flow
