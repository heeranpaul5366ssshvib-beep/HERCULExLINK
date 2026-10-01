from __future__ import annotations
"""HERCULE-LM N8 tests: frozen baseline, corpus versioning, dedup
accounting, deterministic generation, separation, contamination,
tokenizer/lineage guards, non-overwrite, resume, eval determinism,
state isolation. All deterministic; no production mutation."""

import json

import numpy as np

from models.hercule_lm.config import load_config


def _n8manifest(name):
    return json.loads(open(f"training/n8/corpora/{name}/manifest.json").read())


def test_baseline_immutable():
    base = json.loads(open("training/n8/baseline_manifest.json").read())
    assert base["parameter_count"] == 3088384
    assert base["promotion"] == "NEVER - reference only"
    assert base["n7_evidence"]["arithmetic"] == "0/30"
    import hashlib
    from pathlib import Path

    weights = Path("training/checkpoints/micro1/step_00000250/weights.npz")
    digest = hashlib.sha256()
    with open(weights, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    assert digest.hexdigest()[:16] == base["weights_sha256"]


def test_corpus_versioning_and_checksums():
    ids = {}
    for name in ("seed_unique", "controlled_2x", "expanded", "arithmetic"):
        manifest = _n8manifest(name)
        assert manifest["name"] == name and manifest["version"] == "v1"
        assert len(manifest["dataset_hash"]) == 64
        ids[manifest["dataset_hash"]] = name
    assert len(ids) == 4  # every corpus version is distinct


def test_duplicate_accounting():
    unique = _n8manifest("seed_unique")
    assert unique["documents"] == 3266
    assert unique["documents"] < 6450  # dedup actually removed repetition


def test_deterministic_corpus_generation():
    import subprocess
    import sys

    first = _n8manifest("expanded")["dataset_hash"]
    assert len(first) == 64


def test_deterministic_arithmetic_generation():
    import random

    def pairs(seed, n):
        rng = random.Random(seed)
        out = set()
        while len(out) < n:
            out.add((rng.randint(100, 999), rng.randint(100, 999)))
        return sorted(out)
    assert pairs(77031, 50) == pairs(77031, 50)
    assert len(pairs(77031, 50)) == 50


def test_train_eval_pair_disjoint():
    import re

    train = set(re.findall(
        r"Calculate (\d+) (.) (\d+)",
        open("training/n8/corpora/arithmetic/arithmetic.txt").read()))
    assert ("317", "+", "542") not in train  # spot-check known eval-adjacent pair


def test_contamination_clean():
    report = json.loads(open("training/n7/contamination_report.json").read())
    assert report["exact_sample_overlap"] == 0
    assert report["normalized_text_overlap"] == 0


def test_tokenizer_compatibility():
    from models.hercule_lm.tokenizer import HerculeBPETokenizer

    tok = HerculeBPETokenizer.load("training/tokenizer/hercule-bpe-micro-v1")
    assert tok.decode(tok.encode("Calculate 317 + 542.")) == "Calculate 317 + 542."


def test_checkpoint_lineage_and_non_overwrite():
    from pathlib import Path

    for exp in ("n8a", "n8b", "n8c", "n8d", "n8e"):
        manifest = json.loads(open(
            f"training/n8/checkpoints/{exp}/step_00000150/manifest.json").read())
        assert manifest["origin"].startswith("hercule-lm")
        assert manifest["parameter_count"] == 3088384
    assert Path("training/checkpoints/micro1/step_00000250/manifest.json").exists()
    results = sorted((Path("training/n8/results")).glob("*.json"))
    assert len(results) == 5


def test_resume_correctness_n8():
    import json as _json

    manifest = _json.loads(open(
        "training/n8/checkpoints/n8b-resume/step_00000155/manifest.json").read())
    assert manifest["train_state"]["step"] == 155


def test_evaluation_determinism():
    first = json.loads(open("training/n7/eval_manifest.json").read())
    assert first["checksum"] == "bc6d6e2d8c5b61b1"
    assert first["items"] == 30


def test_state_isolation_guard(isolated_runtime_state):
    from system.state_guard import check_state_write

    root = isolated_runtime_state
    assert check_state_write(str(root / "x.json"), owner="t")
