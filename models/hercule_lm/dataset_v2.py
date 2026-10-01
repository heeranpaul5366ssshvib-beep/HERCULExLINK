from __future__ import annotations
"""Next-generation dataset pipeline (Phase 4H): auditable, deterministic.

Builds on :mod:`models.hercule_lm.data` (sources, validation, splits,
manifests, shingle near-dup, quality dimensions, sharded streams) by
adding the pieces Phase 4 requires:

- language identification (heuristic, script-based; labeled as such)
- per-document quality scoring (documented formula, deterministic)
- exact dedup (keeps first occurrence, reports removals)
- near-dedup filtering (reuses shingle-Jaccard groups)
- contamination scan against probe texts (explicit probe list)
- declarative filtering (length / repetition / language / license)
- shard writer (.npy token shards + manifest, resumable-cursor ready)
- one orchestrator: ``build_dataset`` -> (docs, splits, manifest, report)

No network, no external models, no pretrained anything. Every
heuristic is documented in the report it produces; sampling (used only
for O(n^2) near-dup on large corpora) is recorded, never hidden.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .data import (DataSource, Document, check_no_leakage, dataset_manifest,
                   near_duplicates, quality_dimensions, split_documents,
                   validate_documents)

# ---------------------------------------------------------------- language

_BENGALI = ("bengali", 0x0980, 0x09FF)
_DEVANAGARI = ("hindi", 0x0900, 0x097F)  # Hindi in Devanagari script
_LATIN = ("latin", 0x0041, 0x007A)


def guess_language(text: str) -> Dict[str, Any]:
    """Heuristic script-based language guess (NOT a trained identifier).

    Counts characters in the Bengali, Devanagari, and Latin ranges plus
    CJK/other; returns the majority script mapped to a language label.
    Mixed content reports ``mixed`` with fractions. Deterministic.
    """
    counts = {"bengali": 0, "hindi": 0, "english": 0, "other": 0}
    total = 0
    for ch in text:
        o = ord(ch)
        if ch.isspace():
            continue
        total += 1
        if 0x0980 <= o <= 0x09FF:
            counts["bengali"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["hindi"] += 1
        elif ch.isascii() and ch.isalpha():
            counts["english"] += 1
        else:
            counts["other"] += 1
    if total == 0:
        return {"language": "unknown", "fractions": {}, "method": "script-heuristic"}
    fracs = {k: round(v / total, 3) for k, v in counts.items()}
    best = max(counts, key=lambda k: counts[k])
    label = best if fracs[best] >= 0.5 else "mixed"
    return {"language": label, "fractions": fracs, "method": "script-heuristic"}


def language_distribution(docs: Sequence[Document]) -> Dict[str, Any]:
    dist: Dict[str, int] = {}
    for doc in docs:
        lang = guess_language(doc.text)["language"]
        dist[lang] = dist.get(lang, 0) + 1
    return {"documents": len(docs), "by_language": dist,
            "method": "script-heuristic (see guess_language)"}


# ---------------------------------------------------------------- quality

def quality_score(text: str) -> Dict[str, Any]:
    """Deterministic per-document quality score in [0, 1].

    Formula (documented, heuristic):
      base 0.5
      +0.2 if 50 <= chars <= 20000 (reasonable length)
      +0.1 if 10 <= words <= 4000
      +0.1 if repetition (dup lines / total lines) < 0.3
      +0.05 for code markers, +0.05 for math markers (content signal)
      -0.3 if > 50% non-alphanumeric noise
    Scores are signals for filtering, never verdicts about truth.
    """
    import re as _re

    chars = len(text)
    words = len(text.split())
    lines = [ln for ln in text.splitlines() if ln.strip()]
    rep = 0.0
    if lines:
        rep = 1.0 - len(set(lines)) / len(lines)
    alnum = sum(1 for c in text if c.isalnum() or c.isspace())
    noise = 1.0 - (alnum / max(1, len(text)))
    score = 0.5
    if 50 <= chars <= 20000:
        score += 0.2
    if 10 <= words <= 4000:
        score += 0.1
    if rep < 0.3:
        score += 0.1
    code_markers = ("def ", "return", "import ", "{", "}", ";", "==")
    math_markers = ("+", "-", "*", "/", "=", "Calculate")
    if any(m in text for m in code_markers):
        score += 0.05
    if any(m in text for m in math_markers):
        score += 0.05
    if noise > 0.5:
        score -= 0.3
    score = max(0.0, min(1.0, round(score, 3)))
    return {"score": score, "chars": chars, "words": words,
            "line_repetition": round(rep, 3), "noise_ratio": round(noise, 3)}


# ---------------------------------------------------------------- dedup

def dedup_exact(docs: Sequence[Document]) -> Tuple[List[Document], Dict[str, Any]]:
    """Drop byte-exact duplicate texts (keep first). Deterministic."""
    seen: Set[str] = set()
    kept: List[Document] = []
    removed = 0
    for doc in docs:
        digest = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
        if digest in seen:
            removed += 1
            continue
        seen.add(digest)
        kept.append(doc)
    return kept, {"input": len(docs), "kept": len(kept), "removed_exact": removed}


def filter_near_duplicates(docs: Sequence[Document], threshold: float = 0.8,
                           k: int = 5, cap: int = 2000) -> Tuple[List[Document], Dict[str, Any]]:
    """Drop near-duplicates (keep first per group). Deterministic.

    ``cap`` bounds the O(n^2) scan: groups are computed on the first
    ``cap`` documents; beyond that the scan is SKIPPED and reported
    (never silently partial).
    """
    if len(docs) > cap:
        return list(docs), {"input": len(docs), "kept": len(docs),
                            "removed_near": 0, "skipped": True,
                            "reason": f"corpus ({len(docs)}) exceeds cap ({cap}); "
                                      "run sharded offline for full near-dedup"}
    groups = near_duplicates(docs, threshold=threshold, k=k)
    drop_ids: Set[str] = set()
    for group in groups:
        for doc_id in sorted(group)[1:]:
            drop_ids.add(doc_id)
    kept = [d for d in docs if d.doc_id not in drop_ids]
    return kept, {"input": len(docs), "kept": len(kept),
                  "removed_near": len(drop_ids), "groups": len(groups),
                  "threshold": threshold, "k": k, "skipped": False}


# ---------------------------------------------------------------- contamination

EVAL_PROBES = [
    "The quick brown fox jumps over the lazy dog",
    "Calculate 317 + 542.",
    "USER: Plan the route.\nTARGET:",
]


def contamination_scan(docs: Sequence[Document],
                       probes: Sequence[str] = (),
                       k: int = 5, threshold: float = 0.8) -> Dict[str, Any]:
    """Shingle-overlap scan of docs against explicit probe texts.

    Reports docs whose word-shingle Jaccard with ANY probe meets the
    threshold. The probe list is part of the report: this checks the
    listed probes only, never "all benchmarks".
    """
    from .data import _shingles

    probes = list(probes) or list(EVAL_PROBES)
    probe_sigs = [_shingles(p, k) for p in probes]
    hits: List[Dict[str, Any]] = []
    for doc in docs:
        sig = _shingles(doc.text, k)
        if not sig:
            continue
        for i, psig in enumerate(probe_sigs):
            if not psig:
                continue
            union = len(sig | psig)
            jac = len(sig & psig) / union if union else 0.0
            if jac >= threshold:
                hits.append({"doc_id": doc.doc_id, "probe": i,
                             "jaccard": round(jac, 3)})
                break
    return {"probes": len(probes), "documents": len(docs),
            "hits": hits, "hit_count": len(hits), "k": k,
            "threshold": threshold,
            "note": "probe-list scan only; extend probes for wider coverage"}


# ---------------------------------------------------------------- filtering

def filter_documents(docs: Sequence[Document],
                     min_chars: int = 20, max_chars: int = 50000,
                     max_rep: float = 0.7, min_score: float = 0.0,
                     allowed_languages: Optional[Sequence[str]] = None,
                     allowed_licenses: Optional[Sequence[str]] = None) -> Tuple[List[Document], Dict[str, Any]]:
    """Declarative filter; every rejection reason is counted."""
    reasons: Dict[str, int] = {}
    kept: List[Document] = []

    def reject(doc: Document, why: str) -> None:
        reasons[why] = reasons.get(why, 0) + 1

    for doc in docs:
        if allowed_licenses is not None and doc.license not in allowed_licenses:
            reject(doc, "license")
            continue
        if not (min_chars <= len(doc.text) <= max_chars):
            reject(doc, "length")
            continue
        info = quality_score(doc.text)
        if info["score"] < min_score or info["line_repetition"] > max_rep:
            reject(doc, "quality")
            continue
        if allowed_languages is not None:
            lang = guess_language(doc.text)["language"]
            if lang not in allowed_languages and "mixed" not in allowed_languages:
                reject(doc, f"language:{lang}")
                continue
        kept.append(doc)
    return kept, {"input": len(docs), "kept": len(kept), "rejected": reasons,
                  "params": {"min_chars": min_chars, "max_chars": max_chars,
                             "max_rep": max_rep, "min_score": min_score,
                             "allowed_languages": list(allowed_languages or []),
                             "allowed_licenses": list(allowed_licenses or [])}}


# ---------------------------------------------------------------- sharding

SHARD_FORMAT = "hercule-shard-v1"


def write_shards(stream, seq_len: int, shard_tokens: int, out_dir: str,
                 prefix: str = "shard") -> Dict[str, Any]:
    """Write a token stream as fixed-size .npy shards + manifest.

    Shard ``i`` holds stream[i*N:(i+1)*N]. Manifest records hashes for
    integrity; ``ShardedStream`` consumes the shards with a resumable
    cursor.
    """
    import numpy as np

    arr = np.asarray(stream, dtype=np.int64)
    total = int(arr.size)
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    shards = []
    for i, start in enumerate(range(0, total, shard_tokens)):
        path = target / f"{prefix}-{i:05d}.npy"
        chunk = np.ascontiguousarray(arr[start:start + shard_tokens])
        tmp = target / f"{prefix}-{i:05d}.tmp.npy"
        np.save(tmp, chunk)
        tmp.replace(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        shards.append({"path": str(path), "tokens": int(chunk.size),
                       "sha256": digest})
    manifest = {"format": SHARD_FORMAT, "seq_len": int(seq_len),
                "total_tokens": total, "shard_tokens": int(shard_tokens),
                "shards": shards}
    (target / "shards.manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


# ---------------------------------------------------------------- orchestrator

def build_dataset(name: str, version: str, sources: Sequence[DataSource],
                  docs: Sequence[Document],
                  allowed_licenses: Sequence[str],
                  min_score: float = 0.0,
                  near_dup_threshold: float = 0.8,
                  probes: Sequence[str] = (),
                  forbidden_hashes: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Full auditable pass: validate -> filter -> dedup -> splits -> manifest.

    Returns {"docs", "splits", "manifest", "leak", "report"} where report
    records every stage's counts and parameters.
    """
    report: Dict[str, Any] = {"name": name, "version": version,
                              "input_documents": len(docs)}
    validate_documents(docs, allowed_licenses, forbidden_hashes)
    kept, freq = filter_documents(docs, min_score=min_score,
                                  allowed_licenses=list(allowed_licenses))
    report["filter"] = freq
    kept, exact = dedup_exact(kept)
    report["dedup_exact"] = exact
    kept, near = filter_near_duplicates(kept, threshold=near_dup_threshold)
    report["dedup_near"] = near
    report["languages"] = language_distribution(kept)
    report["quality"] = quality_dimensions(kept)
    scores = [quality_score(d.text)["score"] for d in kept]
    report["score_hist"] = {
        "n": len(scores),
        "mean": round(sum(scores) / max(1, len(scores)), 3),
        "lt_0_5": sum(1 for s in scores if s < 0.5),
        "ge_0_8": sum(1 for s in scores if s >= 0.8),
    }
    report["contamination"] = contamination_scan(kept, probes)
    splits = split_documents(kept)
    leak = check_no_leakage(splits)
    if leak["overlap"]:
        raise ValueError(f"DATASET LEAKAGE: {leak['overlap'][:3]}")
    report["splits"] = leak["sizes"]
    manifest = dataset_manifest(name, version, sources, kept, splits)
    report["dataset_hash"] = manifest["dataset_hash"]
    return {"docs": kept, "splits": splits, "manifest": manifest,
            "leak": leak, "report": report}
