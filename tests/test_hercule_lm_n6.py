from __future__ import annotations
"""HERCULE-LM N6 tests: hardware gate, init proof, lineage defense,
frozen identities, sanity training, state isolation.

No 100M training is attempted here (gate blocks it); the tests
prove the gate, the guards, and the frozen artifacts instead.
"""

import json

import numpy as np
import pytest

from models.hercule_lm.config import load_config
from models.hercule_lm.model import HerculeLM
from training.n6.hardware_gate import audit_hardware, evaluate_gate


def test_gate_blocks_this_machine():
    hardware = audit_hardware()
    assert hardware["cuda"] is False
    verdict = evaluate_gate(hardware)
    assert verdict["status"] == "BLOCKED"
    codes = [c[0] for c in verdict["checks"]]
    assert "BLOCKED_NO_CUDA" in codes
    assert "BLOCKED_IMPRACTICAL_TIMELINE" in codes
    assert verdict["target_tokens"] == 2_000_000_000


def test_gate_ready_path_with_capable_hardware():
    hardware = {"cuda": True, "ram_free_mb": 20000.0}
    verdict = evaluate_gate(hardware, target_tokens=1_000_000,
                            max_days=30.0, measured_tok_s=1000.0,
                            measured_peak_mb=1000.0, measured_free_mb=20000.0,
                            min_free_mb=6000.0)
    assert verdict["status"] == "READY"


def test_gate_ram_floor_triggers():
    hardware = {"cuda": True, "ram_free_mb": 100.0}
    verdict = evaluate_gate(hardware, measured_peak_mb=100.0,
                            measured_free_mb=100.0)
    assert verdict["status"] == "BLOCKED"
    assert any(c[0] == "BLOCKED_INSUFFICIENT_RAM" for c in verdict["checks"])


def test_100m_config_frozen_and_counted():
    cfg = load_config("hercule_lm_100m")
    assert cfg.parameter_count() == 100093184
    assert cfg.architecture_hash() == "2de3e5574a3bb715"
    assert cfg.vocab_size == 16384 and cfg.context_length == 512


def test_run_config_frozen(tmp_path=None):
    del tmp_path
    run = json.loads(open("training/n6/run_config.json").read())
    assert run["status"] == "BLOCKED_NEVER_STARTED"
    assert run["parameter_count"] == 100093184
    assert run["target_tokens"] == 2_000_000_000
    assert run["seed"] == 20260613
    assert run["tokenizer_checksum"] == "843534c8f576ecde"


def test_init_proof_random_and_finite():
    proof = json.loads(open("training/n6/init_proof.json").read())
    assert proof["weights_origin"] == "RANDOM_INITIALIZATION"
    assert proof["pretrained_weights"] is False
    assert proof["parameter_count"] == 100093184
    for group, stats in proof["param_stats"].items():
        assert stats["finite"] is True, group
        # Xavier matrices ~ N(0, small); norm gammas are ones by design.
        assert min(abs(stats["mean"]), abs(stats["mean"] - 1.0)) < 0.05, group
        assert stats["std"] >= 0.0, group


def test_lineage_rejects_foreign_checkpoint(tmp_path):
    cfg = load_config("hercule_lm_nano")
    model = HerculeLM(cfg, seed=1)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "manifest.json").write_text(json.dumps({
        "architecture": cfg.as_dict(),
        "architecture_hash": cfg.architecture_hash(),
        "origin": "converted from external-weights-v1"}), encoding="utf-8")
    import numpy as np

    np.savez_compressed(foreign / "weights.npz",
                        **{k: np.asarray(v, dtype=np.float32)
                           for k, v in model.params.items()})
    from models.hercule_lm import checkpoint as ckpt

    with pytest.raises(ValueError, match="CHECKPOINT_MISMATCH"):
        ckpt.load_checkpoint(str(foreign), HerculeLM(cfg, seed=1), strict=True)


def test_tokenizer_frozen_identity():
    from models.hercule_lm.tokenizer import HerculeBPETokenizer

    tok = HerculeBPETokenizer.load("training/tokenizer/hercule-bpe-100m-v1")
    assert tok.checksum() == "843534c8f576ecde"
    assert tok.vocab_size == 3736
    assert tok.decode(tok.encode("Calculate 317 + 542.")) == "Calculate 317 + 542."


def test_sanity_training_still_green():
    cfg = load_config("hercule_lm_nano")
    model = HerculeLM(cfg, seed=21)
    rng = np.random.default_rng(5)
    xs = rng.integers(0, 512, size=(2, 16))
    ys = rng.integers(0, 512, size=(2, 16))

    def loss_now():
        logits, cache = model.forward(xs)
        value, _ = model.loss_and_backward(logits, cache, ys)
        return value

    before = loss_now()
    for _ in range(10):
        logits, cache = model.forward(xs)
        _, grads = model.loss_and_backward(logits, cache, ys)
        model.adamw_step(grads, 3e-3)
    assert loss_now() < before


def test_state_isolation_guard(isolated_runtime_state):
    from system.state_guard import check_state_write

    root = isolated_runtime_state
    assert check_state_write(str(root / "x.json"), owner="t")
