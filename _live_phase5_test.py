from __future__ import annotations
"""HERCULE Phase 5 (Decision Intelligence) — live validation + benchmark.

Runs the five spec scenarios through the REAL runtime (Ollama) and prints
honest results: decisions taken, recovery behavior, and measured decision
latency. No fabricated values: any unavailable number is reported as None.
"""

import json
import sys
import time

from runtime.initializer import RuntimeInitializer

RESULTS: dict = {"scenarios": {}, "benchmark": {}}


def _decision_info(brain, correlation_id):
    try:
        trace = brain._tracer.get(correlation_id).as_dict()["stages"]
    except Exception:
        return {}
    return (trace.get("decision") or [{}])[-1] if trace.get("decision") else {}


def scenario(name, brain, goal, expect_mode_prefix=None):
    print(f"\n=== {name}: {goal!r}")
    t0 = time.perf_counter()
    result = brain.run_cycle(goal)
    wall = round(time.perf_counter() - t0, 2)
    decision = result.get("decision") or _decision_info(brain, result.get("correlation_id", ""))
    record = {
        "status": result.get("status"),
        "plan_mode": result.get("plan_mode"),
        "verification": result.get("verification", {}),
        "replans": result.get("replans"),
        "latency_ms": result.get("latency_ms"),
        "decision": decision,
        "wall_s": wall,
    }
    RESULTS["scenarios"][name] = record
    print(f"status={record['status']} plan_mode={record['plan_mode']} "
          f"verified={record['verification'].get('passed_steps')} "
          f"replans={record['replans']} wall={wall}s")
    if decision:
        print(f"decision: candidates={decision.get('candidates')} "
              f"selected={decision.get('selected_strategy')} "
              f"scores={ {k: round(v, 2) for k, v in (decision.get('scores') or {}).items()} }")
        print(f"reason: {str(decision.get('selection_reason', ''))[:140]}")
    return record


def main():
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    orch = services["orchestrator"]
    models = getattr(orch, "models", None)
    print(f"model={getattr(models, 'default_model', '?')} provider=ollama")

    # §19.1 — simple deterministic strategy
    r1 = scenario("1_simple_file", brain, "Create a file named decision_test.txt.")
    # §19.2 — strategy with explicit verification
    r2 = scenario("2_write_verify", brain,
                  'Create a file named decision_test2.txt, write "HERCULE" into it, '
                  "read it back and verify it.")
    # §19.3 — two valid strategies recorded (cognitive policy forced on)
    import os
    os.environ["HERCULE_COGNITIVE_PLANNING"] = "always"
    r3 = scenario("3_two_valid_strategies", brain, "calculate 25 * 4 then calculate 3 + 3")
    os.environ["HERCULE_COGNITIVE_PLANNING"] = "never"
    # §19.4 — safe recoverable failure → decision-ranked recovery
    from abilities.base_ability import BaseAbility

    class FlakyLive(BaseAbility):
        def __init__(self):
            super().__init__("flaky-live", "fails once then succeeds")
            self.calls = 0

        def execute(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient tool fault (planned)")
            return {"status": "success", "content": "recovered-live-content"}

    orch.abilities.ensure_defaults()
    flaky = FlakyLive()
    orch.abilities.register(flaky)
    brain.register_capability("MATH", "tool", "flaky-live")
    math_ok = orch.abilities.exists("mathematics")
    if math_ok:
        orch.abilities.disable("mathematics")
        orch.abilities.disable("calculator")
    try:
        t0 = time.perf_counter()
        r4 = brain.run_cycle("Calculate the totals", payload_fn=lambda step: "6*7",
                             correlation_id="phase5-recover")
        r4_wall = round(time.perf_counter() - t0, 2)
    finally:
        if math_ok:
            orch.abilities.enable("mathematics")
            orch.abilities.enable("calculator")
    RESULTS["scenarios"]["4_recoverable_failure"] = {
        "status": r4.get("status"), "replans": r4.get("replans"),
        "verification": r4.get("verification", {}), "wall_s": r4_wall,
        "flaky_calls": flaky.calls}
    print(f"\n=== 4_recoverable_failure: status={r4.get('status')} "
          f"replans={r4.get('replans')} verified={r4.get('verification', {}).get('passed_steps')} "
          f"flaky_calls={flaky.calls} wall={r4_wall}s")

    # §19.5 — high-risk vs lower-risk equivalent: decision-layer check
    from cognition.decision import CandidateStrategy, decide_strategies
    from cognition.capabilities.capability import Capability
    caps = [c.value for c in Capability]
    risky = CandidateStrategy(
        strategy_id="high-risk-terminal", goal="deploy config",
        steps=[{"step_id": "s1", "goal": "run system change",
                "required_capabilities": ["TERMINAL_EXECUTE"],
                "verification_criteria": ["exit code"]}],
        required_capabilities=["TERMINAL_EXECUTE"], risk="HIGH",
        verification_difficulty="STANDARD", expected_success=0.95,
        estimated_latency_s=10)
    safe = CandidateStrategy(
        strategy_id="low-risk-file", goal="deploy config",
        steps=[{"step_id": "s1", "goal": "read the existing config",
                "required_capabilities": ["FILE_READ"],
                "verification_criteria": ["content non-empty"]}],
        required_capabilities=["FILE_READ"], risk="LOW",
        verification_difficulty="STRONG", estimated_latency_s=30)
    rec = decide_strategies("deploy config", [risky, safe],
                            available_capabilities=caps)
    RESULTS["scenarios"]["5_risk_comparison"] = {
        "selected": rec.selected.strategy_id if rec.selected else None,
        "scores": dict(rec.scores),
        "reason": rec.selection_reason}
    print(f"\n=== 5_risk_comparison: selected={rec.selected.strategy_id} "
          f"scores={ {k: round(v, 2) for k, v in rec.scores.items()} }")

    # §20 benchmark: real measured values from the runs above
    lat = [s.get("latency_ms") for s in RESULTS["scenarios"].values()
           if isinstance(s.get("latency_ms"), (int, float))]
    dtimes = [s.get("decision", {}).get("decision_time_ms")
              for s in RESULTS["scenarios"].values()
              if isinstance(s.get("decision"), dict)]
    dtimes = [d for d in dtimes if isinstance(d, (int, float)) and d >= 0]
    n_cands = [s.get("decision", {}).get("candidates")
               for s in RESULTS["scenarios"].values()
               if isinstance(s.get("decision"), dict)]
    n_cands = [n for n in n_cands if isinstance(n, int)]
    RESULTS["benchmark"] = {
        "model": getattr(models, "default_model", None),
        "provider": "ollama",
        "decision_latency_ms_measured": sorted(dtimes) or None,
        "candidates_per_decision": n_cands or None,
        "candidate_rejections": sum(
            len(s.get("decision", {}).get("rejected_candidates") or [])
            for s in RESULTS["scenarios"].values()
            if isinstance(s.get("decision"), dict)),
        "strategy_successes": sum(
            1 for s in RESULTS["scenarios"].values()
            if s.get("status") == "completed"),
        "strategy_attempts": len(RESULTS["scenarios"]),
        "recovery_success": RESULTS["scenarios"]["4_recoverable_failure"]["status"] == "completed",
        "recovery_replans": RESULTS["scenarios"]["4_recoverable_failure"].get("replans"),
        "run_latencies_ms": lat or None,
    }
    print("\n=== BENCHMARK (measured)")
    print(json.dumps(RESULTS["benchmark"], indent=2, default=str))

    with open("_phase5_live_results.json", "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print("\nsaved -> _phase5_live_results.json")


if __name__ == "__main__":
    sys.exit(main())
