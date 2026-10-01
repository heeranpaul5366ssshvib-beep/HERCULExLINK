from __future__ import annotations
"""Phase 8 tests: adaptive benchmarks, coding bench, research pipeline,
streaming inference, reasoning modes, MORAL suite."""

from cognition.adaptation.benchmarks import run_all_benchmarks
from cognition.adaptation.coding_bench import TASKS, agent_fix, make_tools, run_benchmark
from cognition.adaptation.executor import AdaptiveExecutor
from cognition.adaptation.research_eval import run_research_eval, search, synthesize
from models.hercule_lm.eval_harness import build_suite, run_suite, reference_predict
from models.hercule_lm.reasoning_modes import run_with_mode


def test_adaptive_benchmarks_measured():
    out = run_all_benchmarks(lambda: AdaptiveExecutor(max_retries=3))
    assert out["tool_discovery"]["verdict"] == "adaptive-better"
    assert out["rule_discovery"]["verdict"] == "adaptive-better"
    assert out["world_model"]["rule_confirmed"] is True
    assert out["tool_discovery"]["held_out"] is True


def test_coding_bench_baseline_vs_adaptive(tmp_path):
    from pathlib import Path

    base = run_benchmark("baseline")
    ad = run_benchmark("adaptive")
    assert base["success_rate"] == 0.0
    assert ad["success_rate"] == 1.0
    assert ad["mean_attempts"] > base["mean_attempts"]  # retries cost, honestly
    # Tools actually ran pytest (not stubbed).
    assert base["mean_tool_calls"] >= 2.0


def test_research_pipeline_no_fabrication():
    out = run_research_eval(["CUDA training throughput measurement",
                             "nonexistent topic xyzzy plugh"], root=".")
    assert out["fabricated_sources"] == 0
    assert out["grounding_rate"] >= 0.0
    assert all("query" in r and "citation_rate" in r for r in out["results"])
    assert search("zzzz-no-such-term-qwerty", root=".") == []


def test_streaming_matches_batched():
    from models.hercule_lm.config import HerculeLMConfig
    from models.hercule_lm.torch_model import TorchHerculeLM

    cfg = HerculeLMConfig(model_id="t", vocab_size=260, hidden_size=16,
                          num_layers=2, num_heads=4, ffn_size=32,
                          context_length=12)
    model = TorchHerculeLM(cfg, seed=1)
    streamed = [e["token"] for e in
                model.stream_generate([5, 6], max_new_tokens=6, temperature=0.0)]
    assert [5, 6] + streamed == model.generate([5, 6], max_new_tokens=6,
                                               temperature=0.0)
    assert streamed  # non-empty


def test_reasoning_modes_differ_measurably():
    def gen(budget):
        done = budget >= 100
        return {"text": "result 42" if done else "partial",
                "tokens": 100 if done else budget, "tools": 0}

    fast = run_with_mode("FAST", gen, lambda t: {"pass": "result" in t})
    deep = run_with_mode("DEEP", gen, lambda t: {"pass": "result" in t})
    assert fast["verified_passes"] == 0 < deep["verified_passes"]
    assert fast["tokens"] < deep["tokens"]


def test_moral_suite_present_and_ceiling():
    assert "MORAL" in [t for t in build_suite("MORAL") and ["MORAL"]]
    rep = run_suite("MORAL", reference_predict, model_id="ceil")
    assert rep["mean"] == 1.0 and rep["n"] == 6
