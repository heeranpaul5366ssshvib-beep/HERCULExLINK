from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Embedding Index
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from typing import Any


class EmbeddingIndex:
    """
    Stores document embeddings.

    Can later be replaced with:
    - FAISS
    - ChromaDB
    - Qdrant
    - Milvus
    """

    def __init__(
        self,
        expected_dim: int | None = None,
    ):

        self._embeddings: dict[str, dict[str, Any]] = {}
        self.expected_dim = expected_dim
        self.index_metadata: dict[str, Any] = {}

    ##################################################

    def set_index_metadata(
        self,
        metadata: dict,
    ):
        """Persist provider/model/dim/normalized/version for this index."""
        metadata = dict(metadata or {})
        dim = metadata.get("dimension", 0)
        if dim and self.expected_dim is not None and int(dim) != self.expected_dim:
            raise ValueError(
                f"EMBEDDING_DIMENSION_MISMATCH: metadata dim {dim} != pinned dim {self.expected_dim}"
            )
        self.index_metadata = metadata
        return dict(self.index_metadata)

    ##################################################

    def get_index_metadata(self):
        return dict(self.index_metadata)

    ##################################################

    def require_dimension(
        self,
        dim: int,
    ):
        """Pin the index to one embedding dimensionality.

        Raises EMBEDDING_DIMENSION_MISMATCH when existing data or a
        previous pin conflicts — incompatible vectors are never
        silently absorbed.
        """
        if dim <= 0:
            raise ValueError("dimension must be positive")
        if self.expected_dim is not None and self.expected_dim != dim:
            raise ValueError(f"EMBEDDING_DIMENSION_MISMATCH: index pinned to dim {self.expected_dim}, got {dim}")
        for document_id, record in self._embeddings.items():
            vector = (record or {}).get("embedding") or []
            if len(vector) != dim:
                raise ValueError(
                    f"EMBEDDING_DIMENSION_MISMATCH: {document_id} has dim {len(vector)}, require {dim}"
                )
        self.expected_dim = dim
        return dim

    ##################################################

    def add(
        self,
        document_id: str,
        embedding: list[float],
        metadata: dict | None = None,
    ):

        if self.expected_dim is not None and len(embedding or []) != self.expected_dim:
            raise ValueError(
                f"EMBEDDING_DIMENSION_MISMATCH: {document_id} has dim {len(embedding or [])}, "
                f"index requires {self.expected_dim}"
            )

        self._embeddings[document_id] = {

            "embedding": embedding,

            "metadata": metadata or {}

        }

    ##################################################

    def get(
        self,
        document_id: str,
    ):

        return self._embeddings.get(document_id)

    ##################################################

    def remove(
        self,
        document_id: str,
    ):

        self._embeddings.pop(document_id, None)

    ##################################################

    def all(self):

        return self._embeddings.copy()

    ##################################################

    def size(self):

        return len(self._embeddings)

    ##################################################

    def clear(self):

        self._embeddings.clear()