from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: memory/vector/vector_memory.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Vector Memory Management
Handles semantic vector embeddings and similarity search.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("HERCULE.Memory.VectorMemory")

class VectorMemory:
    """
    Manages vector storage and similarity lookup for HERCULE.

    backend="auto" prefers FAISS, "faiss" requires it, "memory" forces
    the pure-Python cosine fallback. ``dim`` pins one dimensionality:
    mismatched vectors raise EMBEDDING_DIMENSION_MISMATCH instead of
    being silently absorbed.
    """

    def __init__(self, dim: int = 64, backend: str = "auto"):
        if dim <= 0:
            raise ValueError("dim must be positive")
        if backend not in ("auto", "faiss", "memory"):
            raise ValueError(f"unknown vector backend: {backend}")
        self.dim = dim
        self.backend_name = backend
        self._backend = None
        self._storage: List[Dict[str, Any]] = []
        if backend in ("auto", "faiss"):
            try:
                from memory.vector.faiss_adapter import FaissAdapter
                self._backend = FaissAdapter(dim=dim)
                logger.info("Initialized VectorMemory with FaissAdapter (dim=%d).", dim)
            except Exception as exc:
                if backend == "faiss":
                    raise
                logger.info("Initialized VectorMemory with in-memory backend (%s).", exc)
        else:
            logger.info("Initialized VectorMemory with in-memory backend (dim=%d).", dim)

    ##################################################
    def _check_dim(self, vector: List[float], where: str) -> None:
        if len(vector or []) != self.dim:
            raise ValueError(
                f"EMBEDDING_DIMENSION_MISMATCH: {where} has dim {len(vector or [])}, store dim {self.dim}"
            )
        for value in vector or []:
            if not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"EMBEDDING_MALFORMED: {where} contains non-finite components")

    ##################################################
    def add(self, text: str, vector: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a text entry and its corresponding vector embedding.
        """
        self._check_dim(vector, f"add({text[:32]!r})")
        if getattr(self, "_backend", None) is not None:
            try:
                self._backend.add(text, vector, metadata)
                return
            except Exception:
                # fallback to in-memory
                pass

        record = {"text": text, "vector": [float(v) for v in vector], "metadata": metadata or {}}
        self._storage.append(record)
        logger.debug(f"Added vector record for text: [{text[:30]}...]")

    ##################################################
    def search(self, query_vector: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search.
        """
        logger.debug(f"Performing vector similarity search for top {top_k} results.")
        self._check_dim(query_vector, "search(query)")
        # If backend present, delegate
        if getattr(self, "_backend", None) is not None:
            try:
                return self._backend.search(query_vector, top_k=top_k)
            except Exception:
                pass
        # Basic cosine similarity implementation over in-memory storage
        def dot(a: List[float], b: List[float]) -> float:
            return sum(x * y for x, y in zip(a, b))

        def norm(a: List[float]) -> float:
            return sum(x * x for x in a) ** 0.5

        results: List[Dict[str, Any]] = []
        q_norm = norm(query_vector) or 1.0
        for rec in self._storage:
            v = rec.get("vector") or []
            if not v:
                score = 0.0
            else:
                # protect against length mismatch
                if len(v) != len(query_vector):
                    # compute over min length
                    m = min(len(v), len(query_vector))
                    score = dot(v[:m], query_vector[:m]) / (q_norm * (norm(v[:m]) or 1.0))
                else:
                    score = dot(v, query_vector) / (q_norm * (norm(v) or 1.0))
            results.append({"score": score, **rec})

        # sort by descending score
        results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        return results[:top_k]

    ##################################################
    ##################################################
    def clear(self) -> None:
        """
        Clear vector storage.
        """
        backend = getattr(self, "_backend", None)
        if backend is not None and hasattr(backend, "clear"):
            try:
                backend.clear()
            except Exception:
                pass
        if getattr(self, "_storage", None) is not None:
            self._storage.clear()
        logger.info("VectorMemory storage cleared.")

    ##################################################
    def __len__(self) -> int:
        backend = getattr(self, "_backend", None)
        if backend is not None and hasattr(backend, "__len__"):
            try:
                return len(backend)
            except Exception:
                pass
        return len(getattr(self, "_storage", []) or [])

    ##################################################
    def persist(self, path: Union[str, Path], index_metadata: Optional[Dict[str, Any]] = None) -> Path:
        """Persist backend + records (dim-tagged) for restore.

        ``index_metadata`` carries provider/model_id/dimension/
        normalized/version and is stored in the manifest for
        compatibility checks on restore.
        """
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        backend = getattr(self, "_backend", None)
        if backend is not None and hasattr(backend, "save"):
            backend.save(target)
        else:
            (target / "records.json").write_text(
                json.dumps({"dim": self.dim, "backend": "memory", "records": self._storage}),
                encoding="utf-8",
            )
        manifest: Dict[str, Any] = {"dim": self.dim, "backend": self.backend_name, "count": len(self)}
        if index_metadata:
            manifest["index_metadata"] = dict(index_metadata)
        (target / "store.json").write_text(json.dumps(manifest), encoding="utf-8")
        return target

    ##################################################
    @classmethod
    def restore(
        cls,
        path: Union[str, Path],
        backend: str = "auto",
        expected: Optional[Dict[str, Any]] = None,
    ) -> "VectorMemory":
        """Restore a persisted store; corrupt/mismatched data raises.

        When ``expected`` (index metadata) is given, stored
        provider/model/dimension/normalized must agree — incompatible
        indexes are rejected, never mixed.
        """
        """Restore a persisted store; corrupt/mismatched data raises."""
        target = Path(path)
        try:
            manifest = json.loads((target / "store.json").read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"vector store restore failed (manifest unreadable): {exc}")
        dim = int(manifest.get("dim", 0))
        if expected:
            problems = []
            stored_meta = manifest.get("index_metadata") or {}
            for field in ("provider", "model_id", "dimension", "normalized"):
                want = expected.get(field)
                if want is None or want == "" or (field == "dimension" and want == 0):
                    continue
                got = stored_meta.get(field)
                if got is None or got == "" or (field == "dimension" and got == 0):
                    continue
                mismatch = (bool(got) != bool(want)) if field == "normalized" else (str(got) != str(want))
                if mismatch:
                    problems.append(f"{field} {got!r} != {want!r}")
            if problems:
                raise ValueError("EMBEDDING_INDEX_INCOMPATIBLE: " + "; ".join(problems))
        if backend in ("auto", "faiss") and (target / "index.faiss").exists():
            from memory.vector.faiss_adapter import FaissAdapter

            loaded = FaissAdapter.load(target)
            if loaded.dim != dim:
                raise ValueError("EMBEDDING_DIMENSION_MISMATCH: restored index dim differs from manifest")
            store = cls(dim=dim, backend="memory")
            store._backend = loaded
            store.backend_name = "faiss"
            return store
        try:
            payload = json.loads((target / "records.json").read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"vector store restore failed (records unreadable): {exc}")
        if int(payload.get("dim", 0)) != dim:
            raise ValueError("EMBEDDING_DIMENSION_MISMATCH: restored records dim differs from manifest")
        store = cls(dim=dim, backend="memory" if backend == "memory" else backend)
        for record in payload.get("records") or []:
            store.add(str(record.get("text", "")), list(record.get("vector") or []), dict(record.get("metadata") or {}))
        return store