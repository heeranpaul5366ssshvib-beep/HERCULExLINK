# Issue 001 — Vector Store & Embedding Pipeline

Priority: High
Estimate: 2–4 person-weeks

Goal
- Provide a pluggable local vector-store backend and an embedding pipeline that supports multiple embedding providers.

Acceptance criteria
- `memory/vector` exposes a concrete DB adapter (e.g., FAISS or Chroma) with CRUD and similarity search.
- `models/embeddings` contains a service that accepts text and returns embeddings via a chosen adapter.
- Integration test demonstrating storing embeddings and retrieving nearest neighbors.

Files to change (suggested)
- `memory/vector/vector_manager.py` — add DB adapter wiring
- `knowledge/embeddings/embedding_index.py` — adapt to use embedding service
- `models/embeddings/embedding_manager.py` — implement pluggable backends

Notes
- Start with an in-process FAISS-backed adapter or an in-repo fallback if FAISS isn't available.
