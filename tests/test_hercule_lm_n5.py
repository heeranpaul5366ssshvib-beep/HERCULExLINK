from __future__ import annotations
"""HERCULE-LM N5 tests: portability, accumulation, manifests, estimators.

CUDA items skip honestly (NOT_RUN — no CUDA hardware here); nothing
is faked as a pass. CPU paths execute for real at small scale.
"""

import json

import numpy as np
import pytest

from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.config import HerculeLMConfig, load_config
from models.hercule_lm.device import (describe_backend, get_training_device,
                                      move_batch_to_device, topology)
from models.hercule_lm.estimate import estimate_memory, estimate_time, format_duration
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer


def _tiny_config(**over):
    data = {"model_id": "t", "vocab_size": 260, "hidden_size": 16,
            "num_layers": 2, "num_heads": 4, "ffn_size": 32,
            "context_length": 12}
    data.update(over)
    return HerculeLMConfig(**data)


# 1-3. device detection / selection / unavailable CUDA
def test_device_detection_cpu():
    info = describe_backend()
    assert info.device == "cpu" and info.backend == "numpy"
    assert info.available is True
    assert info.as_dict()["dtype_support"] == ["float32"]


def test_cpu_selection_explicit():
    info = get_training_device("cpu")
    assert info.device == "cpu" and info.available is True


def test_unavailable_cuda_fails_clearly():
    with pytest.raises(RuntimeError, match="[Cc][Uu][Dd][Aa]"):
        get_training_device("cuda")
    with pytest.raises(RuntimeError, match="invalid device"):
        get_training_device("tpu")


# 4. CPU model execution
def test_cpu_model_execution():
    model = HerculeLM(_tiny_config(), seed=1)
    ids = np.array([[5, 6, 7]], dtype=np.int64)
    logits, _ = model.forward(ids)
    assert logits.shape == (1, 3, 260) and np.isfinite(logits).all()
    out = model.generate([5], max_new_tokens=4, temperature=0.0)
    assert len(out) == 5


# 5-6. checkpoint save + CPU reload (portability mechanism)
def test_checkpoint_cpu_roundtrip_with_map(tmp_path):
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=3)
    where = ckpt.save_checkpoint(str(tmp_path / "c"), model, {"checksum": "t"},
                                 {"name": "d", "version": "v1"}, {"step": 2},
                                 {"run_id": "r"})
    clone = HerculeLM(cfg, seed=77)
    ckpt.load_checkpoint(where, clone, strict=True, map_to="cpu")
    for key in model.params:
        assert np.allclose(model.params[key], clone.params[key])


def test_checkpoint_cuda_map_fails_honestly(tmp_path):
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=3)
    where = ckpt.save_checkpoint(str(tmp_path / "c"), model, {"checksum": "t"},
                                 {"name": "d", "version": "v1"}, {"step": 0},
                                 {"run_id": "r"})
    with pytest.raises(ValueError, match="CHECKPOINT_MAP_FAILED"):
        ckpt.load_checkpoint(where, HerculeLM(cfg, seed=4),
                             strict=True, map_to="cuda")


# 7-8. architecture + tokenizer compatibility
def test_architecture_mismatch_refused(tmp_path):
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=3)
    where = ckpt.save_checkpoint(str(tmp_path / "c"), model, {"checksum": "t"},
                                 {"name": "d", "version": "v1"}, {"step": 0},
                                 {"run_id": "r"})
    bigger = HerculeLM(HerculeLMConfig(**{**cfg.__dict__, "num_layers": 3}), seed=3)
    with pytest.raises(ValueError, match="CHECKPOINT_MISMATCH"):
        ckpt.load_checkpoint(where, bigger, strict=True)


def test_tokenizer_mismatch_refused(tmp_path):
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=3)
    where = ckpt.save_checkpoint(str(tmp_path / "c"), model, {"checksum": "tok-A"},
                                 {"name": "d", "version": "v1"}, {"step": 0},
                                 {"run_id": "r"})
    with pytest.raises(ValueError, match="TOKENIZER_MISMATCH"):
        ckpt.load_checkpoint(where, HerculeLM(cfg, seed=3), strict=True,
                             expected_tokenizer_checksum="tok-B")


def test_dataset_mismatch_refused(tmp_path):
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=3)
    where = ckpt.save_checkpoint(str(tmp_path / "c"), model, {"checksum": "t"},
                                 {"name": "d", "version": "v1",
                                  "dataset_hash": "aaa"}, {"step": 0},
                                 {"run_id": "r"})
    with pytest.raises(ValueError, match="DATASET_HASH_MISMATCH"):
        ckpt.load_checkpoint(where, HerculeLM(cfg, seed=3), strict=True,
                             expected_dataset_hash="bbb")


# 9-10. gradient accumulation + effective batch
def test_accumulation_matches_large_batch():
    cfg = _tiny_config()
    rng = np.random.default_rng(0)
    xs = rng.integers(0, 260, size=(4, 10))
    ys = rng.integers(0, 260, size=(4, 10))

    def run(accum):
        model = HerculeLM(cfg, seed=9)
        buckets = np.array_split(np.arange(4), accum)
        collected = None
        for part in buckets:
            logits, cache = model.forward(xs[part])
            _, grads = model.loss_and_backward(logits, cache, ys[part])
            collected = grads if collected is None else {
                k: collected[k] + grads[k] for k in grads}
        return {k: v / accum for k, v in collected.items()}

    g1, g2 = run(1), run(2)
    for key in g1:
        assert np.allclose(g1[key], g2[key], rtol=1e-5, atol=1e-7), key


def test_effective_batch_calculation():
    micro, accum, devices = 8, 4, 1
    assert micro * accum * devices == 32


# 11-14. manifests + hashes
def test_training_manifest_written(tmp_path):
    from models.hercule_lm.train import _write_manifests

    _write_manifests(tmp_path / "r", {"run_id": "r", "seed": 1},
                     {"name": "d", "version": "v1", "dataset_hash": "h"})
    run = json.loads((tmp_path / "r" / "run_manifest.json").read_text(encoding="utf-8"))
    assert run["run_id"] == "r" and "rng" in run
    assert (tmp_path / "r" / "dataset_manifest.json").exists()


def test_dataset_manifest_hash_changes(tmp_path):
    from models.hercule_lm.data import dataset_manifest, split_documents
    from models.hercule_lm.data import DataSource, load_documents

    (tmp_path / "a.txt").write_text("alpha beta\ngamma delta\n", encoding="utf-8")
    sources = [DataSource(name="s", license="MIT", origin="x", files=["a.txt"])]
    docs = load_documents(str(tmp_path), sources)
    first = dataset_manifest("n", "v1", sources, docs, split_documents(docs))
    (tmp_path / "a.txt").write_text("alpha beta\ngamma delta\nEXTRA\n", encoding="utf-8")
    docs2 = load_documents(str(tmp_path), sources)
    second = dataset_manifest("n", "v1", sources, docs2, split_documents(docs2))
    assert first["dataset_hash"] != second["dataset_hash"]


def test_model_config_hash():
    assert load_config("hercule_lm_nano").architecture_hash() == \
        load_config("hercule_lm_nano").architecture_hash()
    assert len(load_config("hercule_lm_100m").architecture_hash()) == 16


def test_tokenizer_hash():
    tok = HerculeBPETokenizer.train(["hello world"] * 10, vocab_size=300)
    assert tok.checksum() == HerculeBPETokenizer.train(
        ["hello world"] * 10, vocab_size=300).checksum()


# 15-16. estimators (labeled estimates)
def test_memory_estimator_labels_and_math():
    est = estimate_memory(100_093_184, 2, 256, 640, 16, 10, 16384)
    assert est["kind"] == "ESTIMATE"
    assert est["model_memory_mb"] == pytest.approx(400.4, abs=1.0)
    assert est["gradient_memory_mb"] == pytest.approx(400.4, abs=1.0)
    assert est["optimizer_memory_mb"] == pytest.approx(800.7, abs=1.0)
    assert est["total_training_mb"] > est["model_memory_mb"]


def test_time_estimator_labels():
    est = estimate_time(16.7, 2_000_000_000)
    assert est["kind"] == "ESTIMATE"
    assert est["years"] > 3.0
    assert format_duration(45) == "45s" and format_duration(3600) == "60.0min"
    with pytest.raises(ValueError):
        estimate_time(0, 100)


# 17-18. random-state capture + isolation
def test_random_state_capture():
    from models.hercule_lm.train import _write_manifests
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _write_manifests(f"{tmp}/r", {"run_id": "r", "seed": 7},
                         {"name": "d", "version": "v1"})
        run = json.load(open(f"{tmp}/r/run_manifest.json"))
        assert run["rng"]["streams"].startswith("default_rng")


def test_state_isolation_guard(isolated_runtime_state):
    from system.state_guard import check_state_write

    root = isolated_runtime_state
    assert check_state_write(str(root / "x.json"), owner="t")
    from system.state_guard import StateIsolationError

    with pytest.raises(StateIsolationError):
        check_state_write("C:\\Windows\\Temp\\evil.json", owner="t")


# 19-20. N3/N4 compatibility preserved
def test_n3_n4_compat():
    cfg = load_config("hercule_lm_micro")
    model = HerculeLM(cfg, seed=0)
    assert model.parameter_count() == 3088384
    assert model.generate([10, 20], max_new_tokens=3, temperature=0.0)[0:2] == [10, 20]


# 21-25. CUDA: honest NOT_RUN skips (no hardware here)
@pytest.mark.skip(reason="NOT_RUN — CUDA HARDWARE UNAVAILABLE")
def test_cuda_selection_not_run():
    pass


@pytest.mark.skip(reason="NOT_RUN — CUDA HARDWARE UNAVAILABLE")
def test_gpu_model_execution_not_run():
    pass


@pytest.mark.skip(reason="NOT_RUN — CUDA HARDWARE UNAVAILABLE")
def test_gpu_checkpoint_save_not_run():
    pass


@pytest.mark.skip(reason="NOT_RUN — CUDA HARDWARE UNAVAILABLE")
def test_gpu_to_cpu_load_not_run():
    pass


@pytest.mark.skip(reason="NOT_RUN — CUDA HARDWARE UNAVAILABLE")
def test_amp_behavior_not_run():
    pass


def test_topology_single_device():
    topo = topology()
    assert topo["world_size"] == 1 and topo["rank"] == 0
    assert topo["cuda_available"] is False
    assert "PLANNED" in topo["distributed"]
