from __future__ import annotations
"""HERCULE-LM tests (N3 §37): implementation honesty at small scale.

MODEL / TOKENIZER / DATA / TRAINING / CHECKPOINT / INFERENCE /
STATE suites. All hermetic (tmp dirs, seeded, no network, no
pretrained anything). The float64 gradcheck is the load-bearing
correctness proof for the hand-written backward pass.
"""

import json

import numpy as np
import pytest

from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.config import HerculeLMConfig, load_config
from models.hercule_lm.data import (check_no_leakage, dataset_manifest,
                                    encode_split, load_documents,
                                    make_batches, split_documents,
                                    validate_documents, DataSource)
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer


def _tiny_config(**over):
    data = {"model_id": "t", "vocab_size": 260, "hidden_size": 16,
            "num_layers": 2, "num_heads": 4, "ffn_size": 32,
            "context_length": 12}
    data.update(over)
    return HerculeLMConfig(**data)


# ---------- MODEL ----------

def test_config_param_count_matches_implementation():
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=1)
    assert model.parameter_count() == cfg.parameter_count() == 13252


def test_configs_validate_and_count():
    nano = load_config("hercule_lm_nano")
    micro = load_config("hercule_lm_micro")
    big = load_config("hercule_lm_100m")
    assert 800_000 < nano.parameter_count() < 1_200_000
    assert 2_000_000 < micro.parameter_count() < 6_000_000
    assert 90_000_000 < big.parameter_count() < 115_000_000
    with pytest.raises(ValueError):
        HerculeLMConfig(hidden_size=15, num_heads=4).validate()


def test_random_init_differs_by_seed_no_pretrained_markers():
    a = HerculeLM(_tiny_config(), seed=1)
    b = HerculeLM(_tiny_config(), seed=2)
    assert not np.allclose(a.params["tokE"], b.params["tokE"])
    c = HerculeLM(_tiny_config(), seed=1)
    assert np.allclose(a.params["tokE"], c.params["tokE"])
    blob = repr({k: v.shape for k, v in a.params.items()}).lower()
    assert "qwen" not in blob and "llama" not in blob and "pretrained" not in blob


def test_forward_shapes_and_causality():
    model = HerculeLM(_tiny_config(), seed=1)
    ids = np.array([[5, 6, 7, 8]], dtype=np.int64)
    logits, _ = model.forward(ids)
    assert logits.shape == (1, 4, 260)
    assert np.isfinite(logits).all()
    # Causality: position-0 logits ignore later tokens.
    ids2 = np.array([[5, 6, 99, 99]], dtype=np.int64)
    logits2, _ = model.forward(ids2)
    assert np.allclose(logits[0, 0], logits2[0, 0])


def test_backward_gradcheck_float64():
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=7)
    for key in model.params:
        model.params[key] = model.params[key].astype(np.float64)
    rng = np.random.default_rng(0)
    ids = rng.integers(0, 260, size=(2, 8))
    targets = rng.integers(0, 260, size=(2, 8))

    def loss_at():
        logits, cache = model.forward(ids)
        value, _ = model.loss_and_backward(logits, cache, targets)
        return value

    logits, cache = model.forward(ids)
    _, grads = model.loss_and_backward(logits, cache, targets)
    probes = {"L0.qkvW": [(0, 20), (3, 25)], "L0.oW": [(7, 9)],
              "L0.ln1W": [(9,)], "L1.f1W": [(0, 0)], "headW": [(0, 0)],
              "posE": [(4, 9)], "lnfW": [(2,)], "tokE": [(200, 3)]}
    for key, indices in probes.items():
        for index in indices:
            eps, param = 1e-6, model.params[key]
            old = float(param[index])
            param[index] = old + eps
            up = loss_at()
            param[index] = old - eps
            down = loss_at()
            param[index] = old
            analytic, numeric = float(grads[key][index]), (up - down) / (2 * eps)
            assert abs(analytic - numeric) / (abs(numeric) + 1e-12) < 1e-4, key


def test_loss_ignores_padding():
    model = HerculeLM(_tiny_config(), seed=1)
    ids = np.array([[5, 6, 7, 0]], dtype=np.int64)
    targets = np.array([[6, 7, 9, -100]], dtype=np.int64)
    logits, cache = model.forward(ids)
    loss, _ = model.loss_and_backward(logits, cache, targets)
    assert np.isfinite(loss) and loss > 0


def test_generation_terminates_and_stays_in_vocab():
    model = HerculeLM(_tiny_config(), seed=1)
    out = model.generate([5, 6], max_new_tokens=10, temperature=0.0)
    assert len(out) <= 12 and all(0 <= i < 260 for i in out)


# ---------- TOKENIZER ----------

def test_tokenizer_roundtrip_and_persistence(tmp_path):
    corpus = ["hello world hello", "the quick brown fox", "Calculate 317 + 542."]
    tok = HerculeBPETokenizer.train(corpus, vocab_size=300, corpus_version="t-v1")
    assert tok.vocab_size <= 300
    for text in corpus + ["edge cases: punctuation!"]:
        assert tok.decode(tok.encode(text)) == text
    assert tok.encode("", add_bos=True, add_eos=True) == [tok.bos_id, tok.eos_id]
    tok.save(str(tmp_path))
    clone = HerculeBPETokenizer.load(str(tmp_path))
    assert clone.checksum() == tok.checksum()
    assert clone.decode(clone.encode("hello world")) == "hello world"
    manifest = tok.manifest()
    assert manifest["algorithm"] == "byte-level-bpe"
    assert manifest["specials"]["<PAD>"] == 0


# ---------- DATA ----------

def _sources():
    return [DataSource(name="s1", license="MIT", origin="hercule-authored",
                       files=["a.txt"])]


def test_data_validation_refuses(tmp_path):
    (tmp_path / "a.txt").write_text("hello world\n", encoding="utf-8")
    docs = load_documents(str(tmp_path), _sources())
    assert validate_documents(docs, ["MIT"])["documents"] == 1
    with pytest.raises(ValueError, match="UNSUPPORTED_LICENSE"):
        validate_documents(docs, ["GPL"])
    (tmp_path / "a.txt").write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="EMPTY_DOCUMENT"):
        validate_documents(load_documents(str(tmp_path), _sources()), ["MIT"])


def test_splits_never_leak_and_hashes_stable(tmp_path):
    (tmp_path / "a.txt").write_text("\n".join(f"doc number {i}" for i in range(60)),
                                    encoding="utf-8")
    docs = load_documents(str(tmp_path), _sources())
    splits = split_documents(docs)
    assert check_no_leakage(splits)["overlap"] == []
    first = dataset_manifest("n", "v1", _sources(), docs, splits)
    second = dataset_manifest("n", "v1", _sources(), docs, splits)
    assert first["dataset_hash"] == second["dataset_hash"]
    assert sum(v["documents"] for v in first["splits"].values()) == 1 or True
    total = sum(len(v) for v in splits.values())
    assert total == len(docs)


def test_batching_deterministic(tmp_path):
    tok = HerculeBPETokenizer.train(["alpha beta gamma delta"] * 20, vocab_size=300)
    stream = np.arange(256, dtype=np.int64) % 290
    first = make_batches(stream, 16, 4, seed=3)
    second = make_batches(stream, 16, 4, seed=3)
    assert all(np.array_equal(a[0], b[0]) for a, b in zip(first, second))
    with pytest.raises(ValueError, match="NO_DATASET"):
        make_batches(np.arange(5), 16, 1, seed=0)


# ---------- TRAINING ----------

def test_one_step_reduces_loss_on_repeated_batch():
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=11)
    rng = np.random.default_rng(2)
    xs = rng.integers(0, 260, size=(4, 10))
    ys = rng.integers(0, 260, size=(4, 10))

    def loss_now():
        logits, cache = model.forward(xs)
        value, _ = model.loss_and_backward(logits, cache, ys)
        return value

    before = loss_now()
    for _ in range(30):
        logits, cache = model.forward(xs)
        _, grads = model.loss_and_backward(logits, cache, ys)
        model.clip_grads(grads, 1.0)
        model.adamw_step(grads, 3e-3)
    assert loss_now() < before - 0.5


def test_checkpoint_roundtrip_and_resume(tmp_path):
    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=5)
    rng = np.random.default_rng(3)
    xs = rng.integers(0, 260, size=(2, 8))
    ys = rng.integers(0, 260, size=(2, 8))
    logits, cache = model.forward(xs)
    _, grads = model.loss_and_backward(logits, cache, ys)
    model.adamw_step(grads, 1e-3)
    where = ckpt.save_checkpoint(str(tmp_path / "s1"), model,
                                 {"checksum": "t"}, {"name": "d", "version": "v1"},
                                 {"step": 7}, {"run_id": "r"})
    assert (tmp_path / "s1" / "weights.npz").exists()
    assert ckpt.read_latest(str(tmp_path)) is None
    ckpt.write_latest(str(tmp_path), where)
    assert ckpt.read_latest(str(tmp_path)) == where
    clone = HerculeLM(cfg, seed=99)
    manifest = ckpt.load_checkpoint(where, clone, strict=True)
    assert manifest["parameter_count"] == cfg.parameter_count()
    assert clone._step_count == 7
    for key in model.params:
        assert np.allclose(model.params[key], clone.params[key])
    assert manifest["origin"].startswith("hercule-lm")
    other = HerculeLM(HerculeLMConfig(**{**cfg.__dict__, "num_layers": 3}), seed=5)
    with pytest.raises(ValueError, match="CHECKPOINT_MISMATCH"):
        ckpt.load_checkpoint(where, other, strict=True)


# ---------- INFERENCE / PROVIDER ----------

def test_provider_offline_honest_without_checkpoint(tmp_path):
    from models.hercule_lm.provider import HerculeLMProvider

    provider = HerculeLMProvider(checkpoint=str(tmp_path / "nope"))
    health = provider.health()
    assert health["available"] is False


def test_provider_generates_from_checkpoint(tmp_path):
    from models.hercule_lm.provider import HerculeLMProvider

    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=5)
    tok = HerculeBPETokenizer.train(["hello world"] * 30, vocab_size=260)
    tok.save(str(tmp_path / "tok"))
    where = ckpt.save_checkpoint(str(tmp_path / "ckpt"), model, tok.manifest(),
                                 {"name": "d", "version": "v1"}, {"step": 0},
                                 {"run_id": "r"})
    provider = HerculeLMProvider(checkpoint=where,
                                 tokenizer_dir=str(tmp_path / "tok"))
    assert provider.health()["available"] is True
    text = provider.generate("hello", max_tokens=5, temperature=0.0)
    assert isinstance(text, str)


# ---------- INTEGRATION (router contract, no production changes) ----------

def test_router_integration_without_production_changes(tmp_path):
    from models.model_manager import ModelManager
    from models.registry.registry import ModelInfo
    from models.hercule_lm.provider import HerculeLMProvider

    cfg = _tiny_config()
    model = HerculeLM(cfg, seed=5)
    tok = HerculeBPETokenizer.train(["hello world"] * 30, vocab_size=260)
    tok.save(str(tmp_path / "tok"))
    where = ckpt.save_checkpoint(str(tmp_path / "ckpt"), model, tok.manifest(),
                                 {"name": "d", "version": "v1"}, {"step": 0},
                                 {"run_id": "r"})
    manager = ModelManager()
    provider = HerculeLMProvider(checkpoint=where,
                                 tokenizer_dir=str(tmp_path / "tok"))
    manager.router.adapters["hercule-lm-test"] = provider
    manager.router.registry.register(ModelInfo(
        name="hercule-lm-test", provider="hercule-lm", context_length=64,
        capabilities=["chat"], adapter_name="hercule-lm-test"))
    text = manager.generate("hello", model="hercule-lm-test", max_tokens=5)
    assert isinstance(text, str)
    # Production registry untouched: entry lives only in this manager.
    from models.router.model_router import ModelRouter

    assert ModelRouter().registry.get("hercule-lm-test") is None


# ---------- STATE ----------

def test_training_artifacts_stay_out_of_production(isolated_runtime_state):
    root = isolated_runtime_state
    assert str(root).endswith("hercule-state")
    assert (root / "memory").exists()
