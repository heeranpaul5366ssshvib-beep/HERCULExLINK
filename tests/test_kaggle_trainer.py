from __future__ import annotations
"""Kaggle trainer tests: bundler, manifest, executor gen, monitor,
artifacts, evaluation bridge, checkpoint gate, controller (CLI faked)."""

import json

import pytest

from tools.kaggle_trainer import manifest as _man
from tools.kaggle_trainer.bundler import build_bundle
from tools.kaggle_trainer.checkpoints import adopt, approved, register
from tools.kaggle_trainer.discover import backend_capability, inventory
from tools.kaggle_trainer.evaluate import deltas
from tools.kaggle_trainer import kaggle_executor as _kx
from tools.kaggle_trainer import monitor as _mon


def test_discover_root_and_backend():
    inv = inventory()
    assert inv["parts"]["models/hercule_lm"] == "present"
    assert "hercule_lm_micro" in inv["configs"]
    caps = backend_capability()
    assert caps["numpy"] is True and caps["torch"] is True
    assert caps["torch_cuda"] is False  # honest on this box


def test_bundle_excludes_and_hashes(tmp_path):
    (tmp_path / "x.txt").write_text("hi", encoding="utf-8")
    out = build_bundle(dest=str(tmp_path / "b"),
                       params={"config": "hercule_lm_micro"})
    assert out["files"] > 10
    man = _man.read_json(tmp_path / "b" / "BUNDLE_MANIFEST.json")
    assert man["format"] == "hercule-kaggle-bundle-v1"
    assert man["params"]["config"] == "hercule_lm_micro"
    assert _man.verify_bundle_manifest(tmp_path / "b")["ok"] is True
    # Exclusions honored.
    rels = [e["path"] for e in man["files"]]
    assert not any("__pycache__" in r or ".venv" in r or r.endswith(".pyc")
                   for r in rels)
    assert not any("kaggle_trainer" in r for r in rels)  # not allowlisted


def test_bundle_refuses_secrets(tmp_path, monkeypatch):
    import tools.kaggle_trainer.bundler as _b

    monkeypatch.setattr(_b, "ALLOW", ("models/hercule_lm",))
    probe = __import__("pathlib").Path("models/hercule_lm") / ".env"
    try:
        probe.write_text("KAGGLE_KEY=abc123", encoding="utf-8")
        with pytest.raises(ValueError, match="BUNDLE_REFUSED"):
            build_bundle(dest=str(tmp_path / "b2"))
    finally:
        if probe.exists():
            probe.unlink()


def test_kernel_metadata_gpu_and_params(tmp_path):
    d = _kx.make_kernel_dir(str(tmp_path / "k"), "user", "slug-x",
                            "title", "ds", {"steps": 100}, gpu=True)
    meta = json.loads((__import__("pathlib").Path(d) / "kernel-metadata.json")
                      .read_text(encoding="utf-8"))
    assert meta["enable_gpu"] == "true"
    assert meta["is_private"] == "true"
    assert meta["kernel_type"] == "script"
    assert meta["dataset_sources"] == ["user/ds"]
    boot = (__import__("pathlib").Path(d) / "bootstrap.py").read_text()
    assert '"steps": 100' in boot  # params baked (no kernel env vars)


def test_monitor_parse_and_classify():
    log = ("step=10/100 loss=2.5000 lr=1e-4 gnorm=1.0 500ms 800tok/s (micro=8x1)\n"
           "torch runtime: backend=torch device=cuda:0 gpu=Tesla_T4 count=1 "
           "peak_vram_bytes=123456789 tok_s_wall=800.0\n")
    prog = _mon.parse_progress(log)
    assert prog == {"step": 10, "loss": 2.5, "tok_s": 800.0,
                    "gpu": "Tesla_T4 x1", "peak_vram_bytes": 123456789}
    assert _mon.classify_failure("error", "REMOTE_FAIL [NO_CUDA]: x")["class"] == "accelerator"
    assert _mon.classify_failure("", "torch.cuda.OutOfMemoryError")["class"] == "oom"
    assert _mon.classify_failure("", "traceback boom")["class"] == "code"
    assert _mon.should_retry({"class": "quota", "transient": True}, 0)["retry"] is True
    assert _mon.should_retry({"class": "code", "transient": False}, 0)["retry"] is False
    assert _mon.should_retry({"class": "quota", "transient": True}, 5)["retry"] is False


def test_artifact_verify_and_report(tmp_path):
    from tools.kaggle_trainer import artifacts as _art

    d = tmp_path / "r"
    d.mkdir()
    (d / "run.log").write_text("step=1/2 loss=1.0", encoding="utf-8")
    (d / "REMOTE_STATUS.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    (d / "smoke.json").write_text("{}", encoding="utf-8")
    (d / "gpu.json").write_text("{}", encoding="utf-8")
    ver = _art.verify_run(str(d))
    assert ver["ok"] is True
    report = _art.write_final_report(str(d), {"run_id": "r", "status": "complete"})
    assert report.endswith("FINAL_REPORT.md")


def test_eval_deltas():
    assert deltas({"MATH": 0.5}, {"MATH": 0.0}) == {"MATH": "IMPROVED"}
    assert deltas({"MATH": 0.0}, {"MATH": 0.0}) == {"MATH": "UNCHANGED"}
    assert deltas({"MATH": 0.0}, {}) == {"MATH": "NOT_COMPARABLE"}


def test_checkpoint_gate(tmp_path, monkeypatch):
    import tools.kaggle_trainer.checkpoints as _c

    monkeypatch.setattr(_c, "REGISTRY", str(tmp_path / "reg.json"))
    _c.register("r1", "/tmp/ck", {"MATH": 0.5})
    assert _c.approved() is None  # never auto-approved
    with pytest.raises(ValueError, match="ADOPT_REFUSED"):
        _c.adopt("r1", "", {})
    row = _c.adopt("r1", "measured gain", {"MATH": "IMPROVED"})
    assert row["approved"] is True and _c.approved()["run_id"] == "r1"


def test_controller_blocked_without_creds(monkeypatch):
    from tools.kaggle_trainer import controller as _ctl

    monkeypatch.setattr(_kx, "creds_ok",
                        lambda: {"ok": False, "reason": "no creds"})
    assert _ctl.cmd_new_run(type("A", (), {"config": "hercule_lm_micro"})()) in (0, 2)
    rec = _ctl.train_remote()
    assert rec["status"] == "blocked" and rec["failure_reason"] == "no creds"
