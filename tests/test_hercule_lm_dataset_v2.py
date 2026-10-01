from __future__ import annotations
"""Dataset v2 pipeline tests (Phase 4H): language, quality, dedup,
contamination, filtering, sharding. All hermetic and fast."""

import numpy as np

from models.hercule_lm.data import DataSource, Document, ShardedStream
from models.hercule_lm.dataset_v2 import (
    build_dataset, contamination_scan, dedup_exact, filter_documents,
    filter_near_duplicates, guess_language, language_distribution,
    quality_score, write_shards)


def _doc(doc_id, text, license="MIT"):
    return Document(doc_id, "s", license, text)


def test_guess_language_scripts():
    assert guess_language("hello world this is english")["language"] == "english"
    assert guess_language("আমি বাংলায় কথা বলি")["language"] == "bengali"
    assert guess_language("मैं हिंदी बोलता हूँ")["language"] == "hindi"
    assert guess_language("")["language"] == "unknown"
    assert guess_language("hello আমি")["method"] == "script-heuristic"


def test_language_distribution_counts():
    docs = [_doc("a", "hello world foo bar"), _doc("b", "আমি বাংলা")]
    dist = language_distribution(docs)
    assert dist["documents"] == 2
    assert dist["by_language"]["english"] == 1
    assert dist["by_language"]["bengali"] == 1


def test_quality_score_documented_bounds():
    good = quality_score("Calculate 317 + 542. def add(a, b): return a + b\n" * 3)
    assert 0.0 <= good["score"] <= 1.0
    assert good["score"] >= 0.8
    empty = quality_score("")
    assert empty["score"] < 0.6
    noisy = quality_score("!!!@@@###$$$%%%^^^&&&***((()))" * 10)
    assert noisy["score"] < good["score"]


def test_dedup_exact_keeps_first():
    docs = [_doc("a", "same text here"), _doc("b", "same text here"),
            _doc("c", "different text here")]
    kept, rep = dedup_exact(docs)
    assert [d.doc_id for d in kept] == ["a", "c"]
    assert rep == {"input": 3, "kept": 2, "removed_exact": 1}


def test_near_dup_filter_and_cap():
    base = "the quick brown fox jumps over the lazy dog near the river bank today"
    docs = [_doc(f"d{i}", base + f" extra word number {i}" if i else base)
            for i in range(6)]
    kept, rep = filter_near_duplicates(docs, threshold=0.5)
    assert rep["skipped"] is False
    assert len(kept) < len(docs) and kept[0].doc_id == "d0"
    big = [_doc(f"x{i}", f"unique content {i} " * 10) for i in range(2100)]
    kept2, rep2 = filter_near_duplicates(big, cap=2000)
    assert rep2["skipped"] is True and len(kept2) == 2100


def test_contamination_scan_probe_only():
    docs = [_doc("a", "The quick brown fox jumps over the lazy dog"),
            _doc("b", "something entirely different about cooking rice")]
    rep = contamination_scan(docs)
    assert rep["hit_count"] == 1
    assert rep["hits"][0]["doc_id"] == "a"
    assert "probe" in rep["hits"][0]


def test_filter_documents_reasons():
    docs = [_doc("ok", "hello world this is a normal document with words"),
            _doc("short", "hi"),
            _doc("badlic", "hello world this is fine", license="GPL")]
    kept, rep = filter_documents(docs, min_chars=10, allowed_licenses=["MIT"])
    assert [d.doc_id for d in kept] == ["ok"]
    assert rep["rejected"]["length"] == 1
    assert rep["rejected"]["license"] == 1


def test_write_shards_and_resumable_cursor(tmp_path):
    stream = np.arange(100, dtype=np.int64)
    manifest = write_shards(stream, seq_len=8, shard_tokens=30,
                            out_dir=str(tmp_path / "sh"))
    assert manifest["total_tokens"] == 100
    assert len(manifest["shards"]) == 4
    assert all(len(s["sha256"]) == 64 for s in manifest["shards"])
    loader = ShardedStream([s["path"] for s in manifest["shards"]])
    first = loader.next_batch(2, 8)
    assert first is not None
    state = loader.state_dict()
    loader2 = ShardedStream([s["path"] for s in manifest["shards"]])
    loader2.load_state_dict(state)
    assert np.array_equal(loader2.next_batch(2, 8)[0], loader.next_batch(2, 8)[0])
    with (tmp_path / "sh" / "shards.manifest.json").open() as fh:
        import json
        assert json.load(fh)["format"] == "hercule-shard-v1"


def test_integration_validates_artifact_without_data_swap():
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/dataset_v2_integration.py"],
        capture_output=True, text=True, cwd="C:\\Users\\hp\\HERCULE",
        timeout=600)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-500:]
    out = json.loads((__import__("pathlib").Path(
        "reports/frontier_program/dataset_v2_integration.json")
        .read_text(encoding="utf-8")))
    assert out["all_pass"] is True
    # Migration is recommended, never executed automatically.
    assert out["migration"]["migrate"] is False
    assert "A/B" in out["migration"]["recommendation"]


def test_build_dataset_end_to_end(tmp_path):
    (tmp_path / "a.txt").write_text(
        "hello world foo bar\n\nCalculate 317 + 542.\n\ndef add(a, b):\n    return a + b\n",
        encoding="utf-8")
    from models.hercule_lm.data import load_documents

    sources = [DataSource(name="s", license="MIT", origin="hercule-authored",
                          files=["a.txt"])]
    docs = load_documents(str(tmp_path), sources, paragraphs=True)
    out = build_dataset("t", "v1", sources, docs, allowed_licenses=["MIT"])
    assert out["leak"]["overlap"] == []
    assert "dataset_hash" in out["manifest"]
    assert out["report"]["dedup_exact"]["kept"] >= 1
    assert "by_language" in out["report"]["languages"]
    assert out["report"]["contamination"]["hit_count"] >= 0
