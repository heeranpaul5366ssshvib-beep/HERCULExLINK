import sys, os
sys.path.insert(0, r'c:\Users\hp\HERCULE')
os.chdir(r'c:\Users\hp\HERCULE')
p = r'c:\Users\hp\HERCULE\_smoke_check.txt'
with open(p, 'w', encoding='utf-8') as f:
    def W(m=""):
        f.write(str(m)+"\n"); f.flush()

    W("=== Smoke Check ===")
    try:
        from tests.support_semantic import SemanticMockModel, entry, payload
        from cognition.capabilities.proposal import parse_proposal_payload
        from cognition.capabilities.semantic import SemanticCapabilityProposer
        from cognition.capabilities.hybrid import resolve_capabilities, HybridMode
        from cognition.capabilities.registry import CapabilityRegistry
        from cognition.capabilities.vocabulary import normalize_name
        from system.config.semantic_config import load_semantic_config
        from cognition.planner.planner import Planner
        from abilities.ability_manager import AbilityManager
        from security.permissions.policy_manager import PolicyManager
        W("Imports: OK")
    except Exception as e:
        W(f"Imports FAIL: {e}")
        import traceback; W(traceback.format_exc())
        sys.exit(1)

    try:
        proposals, warnings, errors = parse_proposal_payload(payload(
            entry("FILE_READ", 0.97, "inspect"), entry("CODE_EDIT", 0.91, "modify", required=False)))
        assert [p.name for p in proposals] == ["FILE_READ", "CODE_EDIT"]
        assert proposals[0].confidence == 0.97
        W("Proposal parsing: OK")
    except Exception as e:
        W(f"Proposal parsing FAIL: {e}"); sys.exit(1)

    try:
        assert normalize_name("read files") == "FILE_READ"
        W("Vocabulary: OK")
    except Exception as e:
        W(f"Vocabulary FAIL: {e}"); sys.exit(1)

    try:
        abilities = AbilityManager(PolicyManager())
        abilities.register_defaults()
        registry = CapabilityRegistry()
        n = registry.register_default_tools(abilities)
        W(f"Registry: {n} registered")
    except Exception as e:
        W(f"Registry FAIL: {e}"); sys.exit(1)

    try:
        det = resolve_capabilities("Read this file", registry=registry,
            policy=abilities.policy, ability_manager=abilities, mode="deterministic")
        assert det.final == ["FILE_READ"], f"Got {det.final}"
        W(f"Deterministic resolve: OK -> {det.final}")
    except Exception as e:
        W(f"Deterministic FAIL: {e}"); sys.exit(1)

    try:
        model = SemanticMockModel(script=[("crash", payload(entry("SYSTEM_OBSERVE", 0.9, "diagnose")))])
        proposer = SemanticCapabilityProposer(model=model, allowed_capabilities=registry.capabilities())
        out = resolve_capabilities("Inspect why my application crashes",
            registry=registry, policy=abilities.policy, ability_manager=abilities,
            mode="hybrid", proposer=proposer)
        assert out.final == ["SYSTEM_OBSERVE"], f"Got {out.final}"
        W(f"Hybrid resolve (implicit): OK -> {out.final}")
    except Exception as e:
        W(f"Hybrid FAIL: {e}"); import traceback; W(traceback.format_exc()); sys.exit(1)

    try:
        planner = Planner()
        first = planner.create_capable_plan("g", ["Read this file", "Calculate totals"])
        assert all(s["semantic_report"] == {} for s in first)
        planner.configure_semantic(mode="hybrid")
        second = planner.create_capable_plan("g", ["Read this file", "Calculate totals"])
        assert [s["required_capabilities"] for s in second] == [s["required_capabilities"] for s in first]
        W("Planner legacy identical: OK")
    except Exception as e:
        W(f"Planner FAIL: {e}"); sys.exit(1)

    try:
        config = load_semantic_config({}, env={})
        assert config.enabled is False and config.min_confidence == 0.5
        env_config = load_semantic_config({}, env={
            "HERCULE_SEMANTIC_ENABLED": "true",
            "HERCULE_SEMANTIC_MODE": "shadow",
            "HERCULE_SEMANTIC_CONFIDENCE": "0.7",
        })
        assert env_config.enabled is True and env_config.shadow is True
        assert env_config.min_confidence == 0.7
        W("Feature flags: OK")
    except Exception as e:
        W(f"Feature flags FAIL: {e}"); sys.exit(1)

    W("=== ALL SMOKE TESTS PASSED ===")
print("DONE")
