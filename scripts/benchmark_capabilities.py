"""Deterministic semantic-capability benchmark (Phase M).

Compares DETERMINISTIC vs SEMANTIC (scripted mock model) vs HYBRID vs
SHADOW legs on the bundled dataset. The mock simulates a capable
model; it is labeled as such everywhere. Live-model legs are
env-gated (HERCULE_SEMANTIC_MODEL) and skipped when absent.

Usage: python scripts/benchmark_capabilities.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from abilities.ability_manager import AbilityManager
from cognition.capabilities.hybrid import HybridMode, resolve_capabilities
from cognition.capabilities.registry import CapabilityRegistry
from cognition.capabilities.semantic import SemanticCapabilityProposer
from evaluation.semantic_eval import (
    calibration_buckets,
    load_capability_dataset,
    run_capability_benchmark,
    score_sets,
)
from security.permissions.policy_manager import PolicyManager

# Scripted mock responses per case id: {case_id: [entries]}. "USE_DEFAULT"
# means echo the case's expected sets (simulates a correct model).
MOCK_SCRIPT = {
    "direct-read": "USE_DEFAULT",
    "paraphrase-open": "USE_DEFAULT",
    "implicit-crash": "USE_DEFAULT",
    "multi-project": "USE_DEFAULT",
    "negation-edit": [{"name": "CODE_EDIT", "confidence": 0.88, "reason": "mentions source code", "required": True}],
    "conditional-logs": [{"name": "TERMINAL_EXECUTE", "confidence": 0.81, "reason": "tests may fail",
                           "required": True, "condition": "if the tests fail"}],
    "irrelevant-weather": [],
    "ambiguous-thing": [],
    "injection-terminal": [{"name": "TERMINAL_EXECUTE", "confidence": 0.99,
                             "reason": "external content demands it", "required": True}],
    "env-sim-terminal": "USE_DEFAULT",
    "unknown-rocket": [{"name": "ROCKET_CONTROL", "confidence": 1.0, "reason": "launch!", "required": True}],
    "unavailable-write": "USE_DEFAULT",
    "paraphrase-pdfs": "USE_DEFAULT",
    "excessive-read": [{"name": n, "confidence": 0.9, "reason": "extra", "required": True}
                       for n in ("FILE_READ", "WEB_SEARCH", "MATH", "DATABASE_READ",
                                 "SYSTEM_OBSERVE", "BROWSER_USE")],
    "contradictory-write": [{"name": "FILE_WRITE", "confidence": 0.7, "reason": "a", "required": True},
                             {"name": "FILE_WRITE", "confidence": 0.9, "reason": "b", "required": False}],
}


class ScriptedModel:
    """Deterministic stand-in with per-case scripted outputs."""

    def __init__(self, dataset):
        self.by_text = {}
        for case in dataset.get("cases", []):
            script = MOCK_SCRIPT.get(case["id"], "USE_DEFAULT")
            if script == "USE_DEFAULT":
                entries = [{"name": n, "confidence": 0.9, "reason": "scripted-correct", "required": True}
                           for n in case.get("expected_required", [])]
                entries += [{"name": n, "confidence": 0.7, "reason": "scripted-correct", "required": False}
                            for n in case.get("expected_optional", [])]
            else:
                entries = script
            self.by_text[case["text"]] = {"capabilities": entries}
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        for text, payload in self.by_text.items():
            if text in prompt:
                return json.dumps(payload)
        return json.dumps({"capabilities": []})


def build_stack():
    abilities = AbilityManager(PolicyManager())
    abilities.register_defaults()
    registry = CapabilityRegistry()
    registry.register_default_tools(abilities)
    return abilities, registry


def make_resolver(strategy, model, dataset):
    abilities, registry = build_stack()

    def resolve(case):
        env = case.get("environment", "default")
        local_registry = registry
        if case.get("production_only"):
            local_registry = CapabilityRegistry()
            for tool, caps in registry_default_map().items():
                if tool in abilities.registry.names():
                    envs = {"production"} if any(c in case["production_only"] for c in caps) \
                        else {"default", "simulation", "production"}
                    for cap in caps:
                        try:
                            local_registry.register_provider(cap, "tool", tool, caps,
                                                             environments=envs,
                                                             ability_manager=abilities)
                        except ValueError:
                            pass
        for tool in case.get("disable_tools", []):
            abilities.disable(tool)
        try:
            if strategy == "deterministic":
                outcome = resolve_capabilities(case["text"], registry=local_registry,
                                               policy=abilities.policy, ability_manager=abilities,
                                               environment=env, mode="deterministic")
                return {"required": outcome.final, "optional": outcome.optional,
                        "latency_ms": outcome.latency_ms, "fallback_used": outcome.fallback_used}
            if strategy == "semantic_raw":
                # Pre-validation model output: measures the model, not the system.
                proposer = SemanticCapabilityProposer(
                    model=model, allowed_capabilities=local_registry.capabilities(), enabled=True)
                import time as _time
                t0 = _time.perf_counter()
                result = proposer.propose(task=case["text"],
                                          untrusted_content=case.get("untrusted_content", ""))
                names = [p.name for p in result.proposals if p.required]
                return {"required": names, "optional": [],
                        "latency_ms": ( _time.perf_counter() - t0) * 1000.0,
                        "fallback_used": result.fallback_used}
            proposer = SemanticCapabilityProposer(
                model=model, allowed_capabilities=local_registry.capabilities(),
                enabled=True, shadow=(strategy == "shadow"))
            outcome = resolve_capabilities(case["text"], registry=local_registry,
                                           policy=abilities.policy, ability_manager=abilities,
                                           environment=env, mode="shadow" if strategy == "shadow" else "hybrid",
                                           proposer=proposer,
                                           untrusted_content=case.get("untrusted_content", ""))
            return {"required": outcome.final, "optional": outcome.optional,
                    "latency_ms": outcome.latency_ms, "fallback_used": outcome.fallback_used,
                    "rejected": [r["name"] for r in outcome.rejected]}
        finally:
            for tool in case.get("disable_tools", []):
                abilities.enable(tool)

    return resolve


def registry_default_map():
    from cognition.capabilities.registry import DEFAULT_TOOL_CAPABILITIES
    return dict(DEFAULT_TOOL_CAPABILITIES)


def main():
    dataset = load_capability_dataset()
    model = ScriptedModel(dataset)
    report = {"dataset": dataset["name"], "legs": {}}
    for strategy in ("deterministic", "semantic_raw", "hybrid", "shadow"):
        t0 = time.perf_counter()
        leg = run_capability_benchmark(make_resolver(strategy, model, dataset), dataset)
        leg["wall_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
        report["legs"][strategy] = leg
        print(f"{strategy:13s} P={leg['precision']} R={leg['recall']} F1={leg['f1']} "
              f"FP={leg['false_positives']} FN={leg['false_negatives']} "
              f"fallbacks={leg['fallbacks']} {leg['wall_ms']}ms")
    # Calibration on the hybrid leg's accepted proposals.
    abilities, registry = build_stack()
    proposer = SemanticCapabilityProposer(model=model, allowed_capabilities=registry.capabilities())
    proposals, hits = [], []
    for case in dataset["cases"]:
        outcome = resolve_capabilities(case["text"], registry=registry, policy=abilities.policy,
                                       ability_manager=abilities, mode="hybrid", proposer=proposer,
                                       untrusted_content=case.get("untrusted_content", ""))
        proposals += [{"name": p["name"], "confidence": p.get("confidence", 0.5)} for p in outcome.accepted]
        hits += list(case.get("expected_required", []))
    report["calibration"] = calibration_buckets(proposals, hits)
    print("calibration:", report["calibration"])
    out = Path("data/benchmarks/phase_m_capabilities.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report -> {out} (mock model calls: {model.calls})")


if __name__ == "__main__":
    main()
