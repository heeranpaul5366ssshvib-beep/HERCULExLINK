from __future__ import annotations
"""HERCULE-LM N4 tests: threads helper, stream cache, determinism,
benchmark schema, scaling counts, memory estimation helpers."""

import json

import numpy as np

from models.hercule_lm.config import load_config
from models.hercule_lm.data import cached_stream
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.threads import configure_threads, desired_threads, physical_cores
from models.hercule_lm.tokenizer import HerculeBPETokenizer


def test_threads_helper_parsing(monkeypatch):
    assert physical_cores() >= 1
    monkeypatch.setenv("HERCULE_LM_THREADS", "3")
    assert desired_threads() == 3
    assert configure_threads() == 3
    import os

    assert os.environ.get("OMP_NUM_THREADS") == "3"
    monkeypatch.setenv("HERCULE_LM_THREADS", "bogus")
    assert desired_threads() == physical_cores()


def test_stream_cache_identical_and_invalidated(tmp_path):
    tok = HerculeBPETokenizer.train(["alpha beta"] * 20, vocab_size=300,
                                    corpus_version="c")
    from models.hercule_lm.data import DataSource, encode_split, load_documents

    (tmp_path / "d.txt").write_text("alpha beta\ngamma delta\n", encoding="utf-8")
    docs = load_documents(str(tmp_path),
                          [DataSource(name="s", license="MIT", origin="x", files=["d.txt"])])
    direct = encode_split(tok, docs, 8)
    first = cached_stream(tok, docs, 8, seed=0, cache_dir=str(tmp_path / "c"),
                          corpus_hash="h1")
    assert np.array_equal(first, direct)
    second = cached_stream(tok, docs, 8, seed=0, cache_dir=str(tmp_path / "c"),
                           corpus_hash="h1")
    assert np.array_equal(second, direct)  # cache hit, identical bytes
    third = cached_stream(tok, docs, 8, seed=0, cache_dir=str(tmp_path / "c"),
                          corpus_hash="h2")
    assert np.array_equal(third, direct)  # invalidated, re-encoded identically
    manifests = list((tmp_path / "c").glob("*.manifest.json"))
    assert len(manifests) == 2


def test_determinism_same_seed_same_loss():
    cfg = load_config("hercule_lm_nano")
    rng = np.random.default_rng(0)
    xs = rng.integers(0, 512, size=(2, 16))
    ys = rng.integers(0, 512, size=(2, 16))
    losses = []
    for _ in range(2):
        model = HerculeLM(cfg, seed=4)
        logits, cache = model.forward(xs)
        loss, grads = model.loss_and_backward(logits, cache, ys)
        model.adamw_step(grads, 1e-3)
        logits, cache = model.forward(xs)
        loss2, _ = model.loss_and_backward(logits, cache, ys)
        losses.append((loss, loss2))
    assert losses[0] == losses[1]


def test_benchmark_output_schema(tmp_path, monkeypatch):
    import subprocess
    import sys

    out = tmp_path / "bench"
    proc = subprocess.run(
        [sys.executable, "-m", "training.benchmark", "--config", "hercule_lm_nano",
         "--steps", "4", "--batch", "2", "--out", str(out)],
        capture_output=True, text=True, cwd="C:\\Users\\hp\\HERCULE", timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    files = list(out.glob("bench_*.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    for key in ("benchmark", "params", "forward_s", "backward_s",
                "tokens_per_sec", "peak_rss_mb", "ckpt_save_s",
                "ckpt_roundtrip_ok", "loss_first", "loss_last"):
        assert key in record, key
    assert record["ckpt_roundtrip_ok"] is True
    assert record["peak_rss_mb"] > 0


def test_scaling_configs_counted():
    expected = {"hercule_lm_nano": (800_000, 1_200_000),
                "hercule_lm_micro": (2_000_000, 6_000_000),
                "hercule_lm_100m": (90_000_000, 115_000_000)}
    for name, (low, high) in expected.items():
        cfg = load_config(name)
        model = HerculeLM(cfg, seed=0)
        assert model.parameter_count() == cfg.parameter_count()
        assert low < cfg.parameter_count() < high, name
