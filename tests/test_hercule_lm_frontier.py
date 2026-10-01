from __future__ import annotations
"""Frontier program tests: roadmap, tokenizer metrics, near-dedup,
quality dims, streaming, SFT masking, batch/top-k/score inference,
orchestrator dry-run, registry lifecycle, context probes."""

import ast
import json

import numpy as np
import pytest

from models.hercule_lm.config import load_config
from models.hercule_lm.data import (ShardedStream, mask_before_marker,
                                    near_duplicates, quality_dimensions)
from models.hercule_lm.estimate import estimate_memory
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer_metrics import measure, probe_categories


def test_roadmap_counts_measured():
    expected = {"hercule-lm-300m": 196079104, "hercule-lm-1b": 783801344,
                "hercule-lm-3b": 2690700288, "hercule-lm-7b": 5183593472}
    for name, count in expected.items():
        assert load_config(name).parameter_count() == count, name


def test_tokenizer_metrics_shape():
    from models.hercule_lm.tokenizer import HerculeBPETokenizer

    tok = HerculeBPETokenizer.train(["hello world"] * 20, vocab_size=300)
    report = measure(tok, ["hello world", "def add(a, b):\n    return a + b"])
    assert report["roundtrip_rate"] == 1.0
    assert report["fertility_tok_per_word"] > 0
    probes = probe_categories(tok)
    assert probes["code"]["roundtrip"] is True
    assert set(probes) >= {"code", "numbers", "punctuation", "whitespace",
                           "multilingual"}


def test_near_duplicates_found_and_reported():
    from models.hercule_lm.data import Document

    docs = [Document(f"d{i}", "s", "MIT", text) for i, text in
            enumerate(["alpha beta gamma delta epsilon",
                       "alpha beta gamma delta epsilon",
                       "alpha beta gamma delta zeta",
                       "completely different words here now"])]
    groups = near_duplicates(docs, threshold=0.8)
    assert groups == [["d0", "d1"]]
    assert near_duplicates(docs[:1]) == []


def test_quality_dimensions_counts():
    from models.hercule_lm.data import Document

    docs = [Document("a", "s", "MIT", "def add(a, b):\n    return a + b"),
            Document("b", "s", "MIT", "Calculate 3 + 4."),
            Document("c", "s", "MIT", "USER:\nDo it.\nTARGET:\nDone.")]
    dims = quality_dimensions(docs)
    assert dims["documents"] == 3
    assert dims["code_like"] == 1 and dims["math_like"] == 2
    assert dims["instructional_like"] == 1
    assert dims["repetition_ratio"] == 0.0


def test_streaming_loader_order_and_cursor(tmp_path):
    stream = np.arange(100, dtype=np.int64)
    np.save(tmp_path / "s0.npy", stream[:60])
    np.save(tmp_path / "s1.npy", stream[60:])
    loader = ShardedStream([str(tmp_path / "s0.npy"), str(tmp_path / "s1.npy")])
    first = loader.next_batch(2, 8)
    assert first is not None
    state = loader.state_dict()
    assert state["offset"] > 0
    clone = ShardedStream([str(tmp_path / "s0.npy"), str(tmp_path / "s1.npy")])
    clone.load_state_dict(state)
    assert clone.state_dict() == state
    rest, count = [], 0
    batch = loader.next_batch(2, 8)
    while batch is not None and count < 20:
        rest.append(batch)
        count += 1
        batch = loader.next_batch(2, 8)
    assert count > 0
    with pytest.raises(ValueError, match="STREAM_MISMATCH"):
        clone.load_state_dict({"shards": ["other.npy"]})
    other = ShardedStream([], rank=1, world_size=2)
    assert other.next_batch(2, 8) is None


def test_sft_masking():
    ids = np.array([[10, 20, 30, 40, 50]])
    masked = mask_before_marker(ids, [30])
    assert list(masked[0, :3]) == [-100, -100, -100]
    assert list(masked[0, 3:]) == [40, 50]
    untouched = mask_before_marker(ids, [999])
    assert (untouched == ids).all()


def test_batch_generate_and_topk_deterministic():
    cfg = load_config("hercule_lm_nano")
    model = HerculeLM(cfg, seed=2)
    first = model.generate_batch([[5, 6], [7]], max_new_tokens=4, temperature=0.0)
    second = model.generate_batch([[5, 6], [7]], max_new_tokens=4, temperature=0.0)
    assert first == second
    assert len(first) == 2 and all(len(o) <= 6 + 4 for o in first)
    sampled = model.generate([5], max_new_tokens=4, temperature=1.0, seed=1,
                             top_k=5, top_p=0.9)
    assert len(sampled) == 5


def test_provider_score_finite(tmp_path):
    from models.hercule_lm import checkpoint as ckpt
    from models.hercule_lm.provider import HerculeLMProvider
    from models.hercule_lm.tokenizer import HerculeBPETokenizer

    cfg = load_config("hercule_lm_nano")
    model = HerculeLM(cfg, seed=2)
    tok = HerculeBPETokenizer.train(["hello world"] * 20, vocab_size=512)
    tok.save(str(tmp_path / "tok"))
    where = ckpt.save_checkpoint(str(tmp_path / "c"), model, tok.manifest(),
                                 {"name": "d", "version": "v1"}, {"step": 0},
                                 {"run_id": "r"})
    provider = HerculeLMProvider(checkpoint=where, tokenizer_dir=str(tmp_path / "tok"))
    value = provider.score("hello", "world")
    assert np.isfinite(value)


def test_code_syntax_check_without_execution():
    snippet = "def add(a, b):\n    return a + b\n"
    assert ast.parse(snippet) is not None
    with pytest.raises(SyntaxError):
        ast.parse("def broken(:\n")


def test_orchestrator_dry_run_micro_ready_and_100m_blocked():
    import subprocess
    import sys

    micro = subprocess.run(
        [sys.executable, "-m", "training.run", "--model", "hercule-lm-micro",
         "--dry-run"], capture_output=True, text=True, cwd="C:\\Users\\hp\\HERCULE",
        timeout=300)
    assert micro.returncode == 0, micro.stdout[-1500:] + micro.stderr[-500:]
    assert "READY" in micro.stdout
    big = subprocess.run(
        [sys.executable, "-m", "training.run", "--model", "hercule-lm-100m",
         "--dry-run"], capture_output=True, text=True, cwd="C:\\Users\\hp\\HERCULE",
        timeout=300)
    assert big.returncode == 2
    assert "BLOCKED" in big.stdout


def test_registry_lifecycle_states():
    registry = json.loads(open("models/registry.json").read())
    by_id = {m["model_id"]: m for m in registry["models"]}
    assert by_id["hercule-lm-micro-v0.1"]["status"] in ("TRAINED", "EXPERIMENTAL")
    assert by_id["hercule-lm-100m-v0.0"]["status"] == "CONFIGURED"
    assert by_id["hercule-lm-100m-v0.0"]["training_status"] == "NOT_TRAINED"
    for model in registry["models"]:
        assert model["origin"].startswith("from_scratch")
        assert "pretrained" not in json.dumps(model).lower() or "no pretrained" in json.dumps(model).lower()


def test_context_probe_shapes():
    cfg = load_config("hercule_lm_micro")
    model = HerculeLM(cfg, seed=0)
    rng = np.random.default_rng(0)
    for length in (32, 64):
        ids = rng.integers(0, 1024, size=(1, length))
        logits, _ = model.forward(ids)
        assert logits.shape == (1, length, 1024)
        assert np.isfinite(logits).all()


def test_metrics_log_writes_valid_jsonl(tmp_path):
    import json
    import subprocess
    import sys

    log = tmp_path / "m.jsonl"
    proc = subprocess.run(
        [sys.executable, "-m", "models.hercule_lm.train", "--config",
         "hercule_lm_nano", "--corpus-dir", "training/data/overfit",
         "--sources", "training/data/overfit/sources.json", "--tokenizer-dir",
         str(tmp_path / "tok"), "--steps", "2", "--batch", "2", "--run-id",
         "metricstest", "--checkpoint-root", str(tmp_path / "ckpt"),
         "--metrics-log", str(log)],
        capture_output=True, text=True, cwd="C:\\Users\\hp\\HERCULE",
        timeout=300)
    assert proc.returncode == 0, proc.stderr[-1500:]
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert lines[0]["step"] == 1 and lines[1]["step"] == 2
    assert all(set(line) >= {"step", "tokens", "loss", "lr", "micro_index"}
               for line in lines)
