from __future__ import annotations
"""Post-training + evaluation tests (Phase 6): data, SFT, verifiers,
preferences, modes, harness, ARC-style, baselines, model cards."""

import json

import pytest

from models.hercule_lm import postdata, verifiers
from models.hercule_lm.baselines import compare, latest_for, record
from models.hercule_lm.eval_harness import (SUITES, build_suite,
                                            model_predict_factory,
                                            reference_predict, run_all,
                                            run_suite, verify_task)
from models.hercule_lm.model_card import generate as make_card
from models.hercule_lm.reasoning_modes import mode_spec, run_with_mode
from models.hercule_lm.sft import (RewardModelInterface, dpo_loss,
                                   preference_record, render_sample,
                                   run_sft)


# ---------- 6A: post-training data ----------

def test_postdata_builds_and_disjoint():
    train = postdata.build_split("train", per_task=4, seed=0)
    evl = postdata.build_split("eval", per_task=4, seed=1)
    assert len(train) == 10 * 4 and len(evl) == 10 * 4
    dis = postdata.verify_disjoint(train, evl)
    assert dis["clean"] is True and dis["overlap"] == []
    rep = postdata.dataset_report(train, evl)
    assert rep["by_task"]["math"] == 8
    assert rep["licenses"] == ["HERCULE-authored (MIT, repo)"]
    assert all(set(s) >= {"id", "task", "source", "license", "version",
                          "prompt", "response", "validated", "contaminated"}
               for s in train)


def test_postdata_save_load_roundtrip(tmp_path):
    train = postdata.build_split("train", per_task=2, seed=0,
                                 tasks=["math", "safety"])
    where = postdata.save_dataset(train, str(tmp_path / "d.json"))
    assert [s["id"] for s in postdata.load_dataset(where)] == \
        [s["id"] for s in train]


# ---------- 6B: SFT ----------

def test_sft_render_and_mask(tmp_path):
    from models.hercule_lm.tokenizer import HerculeBPETokenizer

    tok = HerculeBPETokenizer.train(["hello world"] * 20 + ["<|response|>"],
                                    vocab_size=280, corpus_version="t")
    samples = [{"prompt": "Calculate 1 + 1.", "response": "2"}]
    text = render_sample(samples[0]["prompt"], samples[0]["response"])
    assert "<|response|>" in text
    out = run_sft(None, samples, tok, seq_len=24, seed=0)
    assert out["pairs"] >= 0 and 0.0 <= out["masked_fraction"] <= 1.0
    assert out["marker_ids"] == tok.encode("<|response|>")


# ---------- 6D/6F/6H: verifiers ----------

def test_verifiers():
    assert verifiers.verify_math("answer 859", "859")["pass"] is True
    assert verifiers.verify_math("answer 860", "859")["pass"] is False
    assert verifiers.verify_json('{"name": "a", "idx": 3}',
                                 {"name": "str", "idx": "int"})["pass"] is True
    assert verifiers.verify_json('{"name": "a"}',
                                 {"name": "str", "idx": "int"})["pass"] is False
    assert verifiers.verify_tool_call(
        '{"tool": "calculator", "arguments": {"a": 1}}',
        ["calculator"])["pass"] is True
    assert verifiers.verify_python_tests(
        "def add(x):\n    return x + 1", [{"call": "add(1)", "expect": 2}])["pass"] is True
    assert verifiers.verify_refusal("I can't comply with that request.")["pass"] is True
    assert verifiers.verify_citation("see [S3] here", "[S3]")["pass"] is True


# ---------- 6G: preferences ----------

def test_dpo_loss_and_reward_interface():
    out = dpo_loss(chosen_logp=-1.0, rejected_logp=-3.0)
    assert out["loss"] > 0 and out["margin"] == pytest.approx(2.0)
    rec = preference_record("p", "good", "bad")
    assert set(rec) >= {"id", "prompt", "chosen", "rejected"}
    rm = RewardModelInterface()
    assert rm.score("q", "42", {"verifier": "math", "reference": "42"})["pass"] is True
    assert rm.score("q", "???", {})["pass"] is None  # no verifier: not a claim


# ---------- 6I: reasoning modes ----------

def test_reasoning_modes_measurable():
    for name in ("FAST", "STANDARD", "DEEP"):
        spec = mode_spec(name)
        assert spec["max_tokens"] > 0
    budgets = {m: mode_spec(m)["max_tokens"] for m in ("FAST", "STANDARD", "DEEP")}
    assert budgets["FAST"] < budgets["STANDARD"] < budgets["DEEP"]

    def gen(budget):
        return {"text": "42", "tokens": min(budget, 2), "tools": 0}

    fast = run_with_mode("FAST", gen, lambda t: {"pass": True})
    deep = run_with_mode("DEEP", gen, lambda t: {"pass": True})
    assert fast["attempts"] == 1  # FAST never validates
    assert deep["verified_passes"] >= 1
    assert set(fast) >= {"mode", "attempts", "tokens", "latency_s"}
    with pytest.raises(ValueError):
        mode_spec("ULTRA")


# ---------- 6J/6K: harness ----------

def test_harness_reference_ceiling():
    rep = run_all(reference_predict, model_id="ceil",
                  suites=["MATH", "STRUCTURED_OUTPUT", "SAFETY", "ARC_STYLE"])
    for suite in ("MATH", "STRUCTURED_OUTPUT", "SAFETY", "ARC_STYLE"):
        assert rep["suites"][suite]["mean"] == 1.0, suite
    assert len(SUITES) == 14


def test_harness_records_provenance():
    rep = run_suite("MATH", reference_predict, model_id="m", checkpoint="c",
                    inference={"temp": 0.0})
    first = rep["results"][0]
    assert first["benchmark"] == "hercule-eval-v1"
    assert first["checkpoint"] == "c"
    assert set(first) >= {"score", "latency_s", "invalid", "error", "detail"}


def test_coding_verifier_tests_candidate_not_reference():
    from models.hercule_lm.eval_harness import verify_task

    task = {"id": "CODING-000", "suite": "CODING", "verifier": "tests",
            "code": "def add0(x):\n    return x + 2",
            "tests": [{"call": "add0(7)", "expect": 9}]}
    assert verify_task(task, "def add0(x):\n    return x + 2")["pass"] is True
    assert verify_task(task, "hello world")["pass"] is False
    assert verify_task(task, "def add0(x):\n    return x + 3")["pass"] is False


def test_arc_style_is_synthetic_not_arc():
    tasks = build_suite("ARC_STYLE")
    assert tasks and all(t["suite"] == "ARC_STYLE" for t in tasks)
    blob = json.dumps(tasks).lower()
    assert "arc-agi" not in blob  # never claims ARC-AGI items


# ---------- 6P: baselines ----------

def test_baselines_compare(tmp_path):
    path = str(tmp_path / "b.json")
    record({"model": "m", "checkpoint": "c1", "benchmark": "v",
            "suites": {"MATH": {"mean": 0.5}}}, path)
    record({"model": "m", "checkpoint": "c2", "benchmark": "v",
            "suites": {"MATH": {"mean": 0.7}}}, path)
    assert latest_for("m", path)["checkpoint"] == "c2"
    assert compare({"benchmark": "v", "suites": {"MATH": {"mean": 0.7}}},
                   {"benchmark": "v",
                    "suites": {"MATH": {"mean": 0.5}}}) == {"MATH": "improved"}
    assert compare({"benchmark": "v2", "suites": {}},
                   {"benchmark": "v", "suites": {}})["status"] == "not-comparable"


# ---------- 6R: model card ----------

def test_model_card_unknowns_honest(tmp_path):
    card = make_card("hercule-lm-nano")
    assert card["parameters"] > 0
    assert card["checkpoint"] == "UNKNOWN (no checkpoint supplied)"
    assert card["benchmarks"] in ("see phase6_eval.json", "NOT_RUN")
    assert any("pretrained" in line or "from-scratch" in line
               for line in [card["lineage"]])
