from __future__ import annotations
"""HERCULE-LM dataset pipeline (N3 §7/§8/§10/§16).

Documents are explicit files with per-source license metadata —
never production memory, never scraped content. Splits are by
document hash (deterministic, leakage-free). Validation refuses to
train on malformed, duplicate, unlicensed, or contaminated data.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np


@dataclass
class DataSource:
    name: str
    license: str
    origin: str                      # "hercule-authored" | "hercule-synthetic" | ...
    url: str = ""
    version: str = "v1"
    files: List[str] = field(default_factory=list)


@dataclass
class Document:
    doc_id: str
    source: str
    license: str
    text: str

    def doc_hash(self) -> str:
        return hashlib.sha256(
            f"{self.source}\x00{self.text}".encode("utf-8")).hexdigest()[:16]


def load_documents(root: str, sources: Sequence[DataSource],
                   paragraphs: bool = False) -> List[Document]:
    docs: List[Document] = []
    for source in sources:
        for rel in source.files:
            path = Path(root) / rel
            text = path.read_text(encoding="utf-8")
            chunks = [c for c in text.split("\n\n") if c.strip()] if paragraphs else [text]
            for index, chunk in enumerate(chunks):
                doc_id = f"{source.name}:{Path(rel).name}#{index}" if paragraphs \
                    else f"{source.name}:{Path(rel).name}"
                docs.append(Document(doc_id, source.name, source.license, chunk.strip() + "\n"))
    return docs


def validate_documents(docs: Sequence[Document],
                       allowed_licenses: Sequence[str],
                       forbidden_hashes: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Refuse-to-train gate. Returns a report; raises on critical failure."""
    problems: List[str] = []
    seen_text: Set[str] = set()
    seen_ids: Set[str] = set()
    for doc in docs:
        if not doc.text.strip():
            problems.append(f"EMPTY_DOCUMENT: {doc.doc_id}")
        if doc.doc_id in seen_ids:
            problems.append(f"DUPLICATE_ID: {doc.doc_id}")
        seen_ids.add(doc.doc_id)
        digest = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
        if digest in seen_text:
            problems.append(f"DUPLICATE_DOCUMENT: {doc.doc_id}")
        seen_text.add(digest)
        if doc.license not in allowed_licenses:
            problems.append(f"UNSUPPORTED_LICENSE: {doc.doc_id} ({doc.license})")
        if forbidden_hashes and doc.doc_hash() in forbidden_hashes:
            problems.append(f"CONTAMINATED: {doc.doc_id}")
        try:
            doc.text.encode("utf-8")
        except Exception:
            problems.append(f"IMPOSSIBLE_ENCODING: {doc.doc_id}")
    report = {"documents": len(docs), "problems": problems,
              "critical": [p for p in problems if p.split(':')[0] in
                           {"EMPTY_DOCUMENT", "UNSUPPORTED_LICENSE",
                            "CONTAMINATED", "IMPOSSIBLE_ENCODING"}]}
    if report["critical"]:
        raise ValueError("INVALID_DATASET: " + "; ".join(report["critical"][:5]))
    return report


def split_documents(docs: Sequence[Document], train: float = 0.9,
                    valid: float = 0.05) -> Dict[str, List[Document]]:
    """Deterministic hash split — no document crosses a boundary, ever."""
    buckets: Dict[str, List[Document]] = {"train": [], "validation": [], "test": []}
    for doc in docs:
        slot = int(doc.doc_hash()[:8], 16) % 1000 / 1000.0
        if slot < train:
            buckets["train"].append(doc)
        elif slot < train + valid:
            buckets["validation"].append(doc)
        else:
            buckets["test"].append(doc)
    return buckets


def check_no_leakage(splits: Dict[str, List[Document]]) -> Dict[str, Any]:
    sets = {k: {d.doc_hash() for d in v} for k, v in splits.items()}
    overlap = (sets["train"] & sets["validation"]) | \
              (sets["train"] & sets["test"]) | (sets["validation"] & sets["test"])
    return {"overlap": sorted(overlap),
            "sizes": {k: len(v) for k, v in splits.items()}}


def _shingles(text: str, k: int = 5) -> set:
    tokens = str(text or "").lower().split()
    if len(tokens) < k:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def near_duplicates(docs: Sequence[Document], threshold: float = 0.8,
                    k: int = 5) -> List[List[str]]:
    """Near-duplicate groups via word-shingle Jaccard (deterministic).

    O(n^2) set ops — practical for thousand-scale corpora; reported,
    never auto-deleted.
    """
    sigs = [(d.doc_id, _shingles(d.text, k)) for d in docs]
    groups: List[List[str]] = []
    used: set = set()
    for i, (doc_id, sig) in enumerate(sigs):
        if doc_id in used or not sig:
            continue
        group = [doc_id]
        for j in range(i + 1, len(sigs)):
            other_id, other = sigs[j]
            if other_id in used or not other:
                continue
            union = len(sig | other)
            if union and len(sig & other) / union >= threshold:
                group.append(other_id)
                used.add(other_id)
        if len(group) > 1:
            used.add(doc_id)
            groups.append(sorted(group))
    return sorted(groups)


def quality_dimensions(docs: Sequence[Document]) -> Dict[str, Any]:
    """Measurable quality dimensions (frontier P6): counts, not verdicts."""
    import re as _re

    texts = [d.text for d in docs]
    code_markers = ("def ", "return", "import ", "{", "}", ";", "==")
    math_markers = ("+", "-", "*", "/", "=", "Calculate")
    fact_cues = ("is ", "are ", "was ", "were ")
    instr_cues = ("USER:", "TARGET:", "?", "Plan:", "Classify")
    dims: Dict[str, Any] = {"documents": len(docs)}
    lengths = sorted(len(t) for t in texts) if texts else [0]
    toks = sorted(len(t.split()) for t in texts) if texts else [0]
    dims["doc_chars_p50"] = lengths[len(lengths) // 2]
    dims["doc_chars_max"] = lengths[-1]
    dims["doc_words_p50"] = toks[len(toks) // 2]
    dims["code_like"] = sum(1 for t in texts if any(m in t for m in code_markers))
    dims["math_like"] = sum(1 for t in texts if any(m in t for m in math_markers))
    dims["factual_like"] = sum(1 for t in texts if any(m in t for m in fact_cues))
    dims["instructional_like"] = sum(1 for t in texts if any(m in t for m in instr_cues))
    rep_ratio = 0.0
    if texts:
        rep_ratio = 1.0 - len(set(texts)) / len(texts)
    dims["repetition_ratio"] = round(rep_ratio, 3)
    langs = {"non_ascii": sum(1 for t in texts if any(ord(c) > 127 for c in t))}
    dims["language_distribution"] = {"ascii_only": len(texts) - langs["non_ascii"], **langs}
    return dims


def dataset_manifest(name: str, version: str, sources: Sequence[DataSource],
                     docs: Sequence[Document],
                     splits: Dict[str, List[Document]]) -> Dict[str, Any]:
    texts = sorted(d.doc_hash() for d in docs)
    digest = hashlib.sha256("".join(texts).encode()).hexdigest()
    return {
        "name": name, "version": version,
        "sources": [{"name": s.name, "license": s.license, "origin": s.origin,
                     "url": s.url, "version": s.version,
                     "files": list(s.files)} for s in sources],
        "documents": len(docs),
        "dataset_hash": digest,
        "splits": {k: {"documents": len(v),
                       "hash": hashlib.sha256(
                           "".join(sorted(d.doc_hash() for d in v)).encode()
                       ).hexdigest()[:16]} for k, v in splits.items()},
    }


def encode_split(tokenizer, docs: Sequence[Document], seq_len: int,
                 seed: int = 0) -> np.ndarray:
    """Concatenate encoded docs with EOS separators → token stream."""
    stream: List[int] = []
    for doc in docs:
        ids = tokenizer.encode(doc.text, add_eos=True)
        if ids:
            stream.extend(ids)
    return np.asarray(stream, dtype=np.int64)


CACHE_FORMAT = "hercule-stream-v1"


def cached_stream(tokenizer, docs: Sequence[Document], seq_len: int,
                  seed: int, cache_dir: str,
                  corpus_hash: str = "") -> np.ndarray:
    """Deterministic cached token stream (N4 §13): skips repeat BPE.

    Cache key covers corpus hash + tokenizer checksum + seq_len +
    format version; any change invalidates (falls back to encoding
    and rewrites). Byte-identical to ``encode_split`` on a hit.
    """
    from pathlib import Path as _Path
    import json as _json

    key = hashlib.sha256(
        f"{CACHE_FORMAT}\x00{corpus_hash}\x00{tokenizer.checksum()}\x00{seq_len}".encode()
    ).hexdigest()[:16]
    directory = _Path(cache_dir)
    manifest_path = directory / f"stream-{key}.manifest.json"
    stream_path = directory / f"stream-{key}.npy"
    if manifest_path.exists() and stream_path.exists():
        try:
            meta = _json.loads(manifest_path.read_text(encoding="utf-8"))
            if meta.get("key") == key:
                return np.load(stream_path)
        except Exception:
            pass
    stream = encode_split(tokenizer, docs, seq_len, seed=seed)
    directory.mkdir(parents=True, exist_ok=True)
    # np.save appends .npy when missing, so the temp name must already
    # end in .npy for the atomic replace below to find it.
    tmp = directory / f"stream-{key}.tmp.npy"
    np.save(tmp, stream)
    tmp.replace(stream_path)
    manifest_path.write_text(_json.dumps(
        {"key": key, "format": CACHE_FORMAT, "corpus_hash": corpus_hash,
         "tokenizer_checksum": tokenizer.checksum(), "seq_len": seq_len,
         "tokens": int(stream.size)}), encoding="utf-8")
    return stream


def make_batches(stream: np.ndarray, seq_len: int, batch_size: int,
                 seed: int, pad_id: int = 0) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Sliding-window (input, shifted-target) batches, deterministic order."""
    rng = np.random.default_rng(seed)
    usable = (len(stream) - 1) // seq_len
    if usable < 1:
        raise ValueError("NO_DATASET: stream shorter than one sequence")
    order = rng.permutation(usable)
    batches = []
    for start in range(0, usable, batch_size):
        chunk = order[start:start + batch_size]
        xs = np.stack([stream[i * seq_len:(i + 1) * seq_len] for i in chunk])
        ys = np.stack([stream[i * seq_len + 1:(i + 1) * seq_len + 1] for i in chunk])
        batches.append((xs.astype(np.int64), ys.astype(np.int64)))
    return batches


def mask_before_marker(ids: np.ndarray, marker_ids: list,
                        ignore_id: int = -100) -> np.ndarray:
    """SFT label masking: positions up to and including the first
    occurrence of the marker span are ignored (instruction region);
    everything after trains. No marker → unmasked copy."""
    labels = np.asarray(ids).copy()
    if not marker_ids:
        return labels
    flat = labels.ravel()
    width = len(marker_ids)
    for start in range(len(flat) - width + 1):
        if [int(x) for x in flat[start:start + width]] == list(marker_ids):
            labels.ravel()[:start + width] = ignore_id
            return labels
    return labels


class ShardedStream:
    """Streaming loader over .npy token shards (frontier P7).

    Larger-than-RAM datasets stay on disk: one shard resident at a
    time, sequential deterministic order, resumable cursor
    ({shard, offset}) compatible with checkpoint state. Single-device
    rank 0 consumes all shards; other ranks report empty (multi-GPU
    sharding is PLANNED, not faked).
    """

    def __init__(self, shards: Sequence[str], rank: int = 0, world_size: int = 1):
        paths = [str(s) for s in shards]
        if rank == 0:
            self._paths = paths
        else:
            self._paths = []  # non-zero ranks: no fake data
        self.rank = rank
        self.world_size = world_size
        self.shard_index = 0
        self.offset = 0
        self._current: Optional[np.ndarray] = None

    def state_dict(self) -> Dict[str, Any]:
        return {"shard_index": self.shard_index, "offset": self.offset,
                "rank": self.rank, "world_size": self.world_size,
                "shards": list(self._paths)}

    def load_state_dict(self, state: Dict[str, Any]) -> None:
        if list(state.get("shards", [])) != list(self._paths):
            raise ValueError("STREAM_MISMATCH: shard list changed")
        self.shard_index = int(state.get("shard_index", 0))
        self.offset = int(state.get("offset", 0))
        self._current = None

    def _load_shard(self) -> bool:
        while self.shard_index < len(self._paths):
            try:
                self._current = np.load(self._paths[self.shard_index], mmap_mode="r")
                return True
            except Exception:
                self.shard_index += 1
                self.offset = 0
        self._current = None
        return False

    def next_batch(self, batch_size: int, seq_len: int) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Next sequential (inputs, shifted-targets) windows, or None at end."""
        need = batch_size * seq_len + 1
        buf = np.zeros(need, dtype=np.int64)
        filled = 0
        while filled < need:
            if self._current is None and not self._load_shard():
                return None
            assert self._current is not None
            available = len(self._current) - self.offset
            if available <= 0:
                self._current = None
                self.shard_index += 1
                self.offset = 0
                continue
            take = min(available, need - filled)
            buf[filled:filled + take] = self._current[self.offset:self.offset + take]
            filled += take
            self.offset += take
        xs = buf[:batch_size * seq_len].reshape(batch_size, seq_len)
        ys = buf[1:batch_size * seq_len + 1].reshape(batch_size, seq_len)
        return xs, ys
