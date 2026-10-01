from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Knowledge Ingestion Pipeline
Author: Heeran Paul
License: MIT
--------------------------------------------

INPUT -> IDENTIFY TYPE -> PARSE -> NORMALIZE -> CHUNK
  -> METADATA -> EMBEDDING -> INDEX -> PROVENANCE

Ownership: KNOWLEDGE. The pipeline writes into the existing
``IndexManager`` (keyword), ``EmbeddingIndex`` (vectors + metadata)
and ``Ontology`` (concepts) owned by ``KnowledgeManager`` — it does
not create a parallel store.

The embedding function is injectable. The default is a deterministic
hash embedding clearly marked as test-grade; production wiring passes
a real provider (e.g. Ollama/transformers) with the same
``Callable[[str], List[float]]`` signature.
"""

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from knowledge.provenance import Provenance, utc_now_iso

EmbedFn = Callable[[str], List[float]]
EmbedBatchFn = Callable[[List[str]], List[List[float]]]

_WS_RE = re.compile(r"\s+")


def identify_content_type(document_id: str, text: str) -> str:
    """Identify a coarse content type from the document id suffix."""
    lowered = document_id.lower()
    for suffix, ctype in (
        (".md", "text/markdown"),
        (".markdown", "text/markdown"),
        (".txt", "text/plain"),
        (".pdf", "application/pdf"),
        (".docx", "application/docx"),
        (".html", "text/html"),
        (".json", "application/json"),
    ):
        if lowered.endswith(suffix):
            return ctype
    if text.lstrip().startswith("{"):
        return "application/json"
    return "text/plain"


def normalize_text(text: str) -> str:
    """Normalize whitespace; preserve case for display, lower only for keys."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 200, overlap: int = 40) -> List[str]:
    """Word-based chunking with overlap. Deterministic, no data loss."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size - 1))
    words = text.split()
    if not words:
        return []
    chunks: List[str] = []
    step = chunk_size - overlap
    for start in range(0, len(words), step):
        piece = words[start : start + chunk_size]
        if not piece:
            break
        chunks.append(" ".join(piece))
        if start + chunk_size >= len(words):
            break
    return chunks


def hash_embed(text: str, dim: int = 64) -> List[float]:
    """Deterministic test-grade embedding (hash buckets, L2-normalized).

    NOT a semantic model — suitable for deterministic unit tests and
    offline demos. Swap in a real provider via ``embed_fn``.
    """
    vec = [0.0] * dim
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        mag = (int.from_bytes(digest[4:8], "little") % 1000) / 1000.0
        vec[idx] += mag
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    position: int
    provenance: Provenance


@dataclass
class IngestionResult:
    document_id: str
    content_type: str
    chunks: List[Chunk] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


class KnowledgeIngestionPipeline:
    """Ingest raw text into keyword index + embedding index + provenance."""

    def __init__(
        self,
        index=None,
        embeddings=None,
        ontology=None,
        embed_fn: Optional[EmbedFn] = None,
        chunk_size: int = 200,
        overlap: int = 40,
        embed_batch_fn: Optional[EmbedBatchFn] = None,
        embed_model_id: str = "hercule-hash-test-v1",
        vector_store=None,
    ):
        self.index = index
        self.embeddings = embeddings
        self.ontology = ontology
        self.embed_fn: EmbedFn = embed_fn or hash_embed
        self.embed_batch_fn = embed_batch_fn
        self.embed_model_id = embed_model_id
        self.vector_store = vector_store
        self.chunk_size = chunk_size
        self.overlap = overlap

    def _embed_all(self, pieces: List[str]) -> List[List[float]]:
        """Batch path when available (one call per document, not per chunk)."""
        if self.embed_batch_fn is not None and len(pieces) > 1:
            produced = self.embed_batch_fn(pieces)
            if len(produced) != len(pieces):
                raise ValueError(
                    f"embedding batch returned {len(produced)} vectors for {len(pieces)} chunks"
                )
            return [list(v) for v in produced]
        return [list(self.embed_fn(piece)) for piece in pieces]

    def ingest(
        self,
        document_id: str,
        text: str,
        source: str = "local",
        origin: str = "ingestion",
        version: str = "1",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestionResult:
        result = IngestionResult(document_id=document_id, content_type=identify_content_type(document_id, text))
        normalized = normalize_text(text)
        if not normalized:
            result.errors.append("empty document after normalization")
            return result
        pieces = chunk_text(normalized, self.chunk_size, self.overlap)
        indexed_at = utc_now_iso()
        try:
            vectors = self._embed_all(pieces)
        except Exception as exc:
            result.errors.append(f"embedding: {exc}")
            return result
        if self.embeddings is not None and vectors and hasattr(self.embeddings, "require_dimension"):
            # Pin the index to this model's dimensionality; a foreign-dim
            # index fails loudly instead of absorbing bad vectors.
            self.embeddings.require_dimension(len(vectors[0]))
        embed_dim = len(vectors[0]) if vectors else 0
        for position, (piece, vector) in enumerate(zip(pieces, vectors)):
            chunk_id = f"{document_id}#c{position}"
            provenance = Provenance(
                source=source,
                origin=origin,
                document_id=document_id,
                chunk_id=chunk_id,
                content_type=result.content_type,
                version=version,
                indexed_at=indexed_at,
                transformation=["normalize", "chunk", f"embed:{self.embed_model_id}"],
                direct=True,
                metadata={
                    **dict(metadata or {}),
                    "embedding_model": self.embed_model_id,
                    "embedding_dim": embed_dim,
                },
            )
            chunk = Chunk(chunk_id=chunk_id, document_id=document_id, text=piece, position=position, provenance=provenance)
            try:
                if self.index is not None:
                    self.index.index_document(chunk_id, piece)
                if self.embeddings is not None:
                    payload = {
                        "text": piece,
                        "embedding_model": self.embed_model_id,
                        "embedding_dim": embed_dim,
                        "provenance": provenance.as_dict(),
                        **(metadata or {}),
                    }
                    self.embeddings.add(chunk_id, vector, payload)
                if self.vector_store is not None:
                    self.vector_store.add(
                        piece,
                        vector,
                        {"chunk_id": chunk_id, "document_id": document_id, "provenance": provenance.as_dict()},
                    )
            except Exception as exc:  # keep partial progress, report the rest
                result.errors.append(f"{chunk_id}: {exc}")
                continue
            result.chunks.append(chunk)
        if self.ontology is not None and result.chunks:
            try:
                self.ontology.add_concept(document_id)
            except Exception as exc:
                result.errors.append(f"ontology: {exc}")
        return result
