from __future__ import annotations
"""Optional FAISS-backed vector store adapter with graceful fallback."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
try:
    import faiss
    import numpy as np
    _HAS_FAISS = True
except Exception:
    _HAS_FAISS = False


class FaissAdapter:
    def __init__(self, dim: int = 64):
        if not _HAS_FAISS:
            raise RuntimeError("faiss not available")
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)  # inner-product (cosine with normalized vectors)
        self.records: List[Dict[str, Any]] = []

    def _as_unit(self, vector: List[float], where: str):
        if len(vector or []) != self.dim:
            raise ValueError(f"EMBEDDING_DIMENSION_MISMATCH: {where} has dim {len(vector or [])}, index dim {self.dim}")
        vec = np.array(vector, dtype="float32")
        if not np.all(np.isfinite(vec)):
            raise ValueError(f"EMBEDDING_MALFORMED: {where} contains non-finite components")
        norm = np.linalg.norm(vec) or 1.0
        return (vec / norm).astype("float32")

    def add(self, text: str, vector: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        vec = self._as_unit(vector, f"add({text[:32]!r})")
        self.index.add(vec.reshape(1, -1))
        self.records.append({"text": text, "vector": [float(v) for v in vector], "metadata": metadata or {}})

    def search(self, query_vector: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
        q = self._as_unit(query_vector, "search(query)")
        D, I = self.index.search(q.reshape(1, -1), top_k)
        results: List[Dict[str, Any]] = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0 or idx >= len(self.records):
                continue
            rec = self.records[idx]
            results.append({"score": float(score), **rec})
        return results

    def clear(self) -> None:
        self.index.reset()
        self.records.clear()

    def __len__(self) -> int:
        return len(self.records)

    def save(self, path: Union[str, Path]) -> Path:
        """Persist index + records (dim-tagged) for restore."""
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(target / "index.faiss"))
        (target / "records.json").write_text(
            json.dumps({"dim": self.dim, "records": self.records}), encoding="utf-8"
        )
        return target

    @classmethod
    def load(cls, path: Union[str, Path]) -> "FaissAdapter":
        """Restore a persisted adapter; corrupt/mismatched data raises."""
        target = Path(path)
        try:
            payload = json.loads((target / "records.json").read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"vector index restore failed (records unreadable): {exc}")
        dim = int(payload.get("dim", 0))
        adapter = cls(dim=dim)
        try:
            adapter.index = faiss.read_index(str(target / "index.faiss"))
        except Exception as exc:
            raise ValueError(f"vector index restore failed (index unreadable): {exc}")
        records = payload.get("records") or []
        if adapter.index.ntotal != len(records):
            raise ValueError(
                f"vector index restore failed: index holds {adapter.index.ntotal} vectors for {len(records)} records"
            )
        adapter.records = records
        return adapter
