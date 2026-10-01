import sys, os
sys.path.insert(0, r'c:\Users\hp\HERCULE')
os.chdir(r'c:\Users\hp\HERCULE')

out_lines = []
def P(msg=""):
    out_lines.append(str(msg))
    print(msg)

P("Testing imports...")
for name, imp in [
    ("proposal", "from cognition.capabilities.proposal import CapabilityProposal, parse_proposal_payload"),
    ("semantic", "from cognition.capabilities.semantic import SemanticCapabilityProposer, render_capability_prompt"),
    ("hybrid", "from cognition.capabilities.hybrid import resolve_capabilities, HybridMode"),
    ("registry", "from cognition.capabilities.registry import CapabilityRegistry"),
    ("vocabulary", "from cognition.capabilities.vocabulary import normalize_name"),
    ("inference", "from cognition.capabilities.inference import infer_capabilities"),
    ("effects", "from cognition.capabilities.effects import default_effect_for"),
    ("planner", "from cognition.planner.planner import Planner"),
    ("capable", "from cognition.planner.capable import build_capable_plan"),
    ("validation", "from cognition.planner.validation import validate_plan"),
    ("semantic_config", "from system.config.semantic_config import load_semantic_config"),
    ("trace", "from system.observability.trace import Tracer, trace_semantic"),
    ("semantic_eval", "from evaluation.semantic_eval import load_capability_dataset, run_capability_benchmark, score_sets"),
    ("brain", "from brain.brain import Brain"),
]:
    try:
        exec(imp, globals())
        P(f"  {name}: OK")
    except Exception as e:
        P(f"  {name}: FAILED {e}")

P("\nRunning quick smoke tests...")
try:
    from tests.support_semantic import entry, payload
    proposals, warnings, errors = parse_proposal_payload(payload(
        entry("FILE_READ", 0.97, "inspect file"), entry("CODE_EDIT", 0.91, "modify", required=False)))
    assert [p.name for p in proposals] == ["FILE_READ", "CODE_EDIT"]
    P("  Proposal parsing: PASSED")
except Exception as e:
    P(f"  Proposal parsing: FAILED {e}")
    import traceback
    P(traceback.format_exc())

try:
    from abilities.ability_manager import AbilityManager
    from security.permissions.policy_manager import PolicyManager
    abilities = AbilityManager(PolicyManager())
    abilities.register_defaults()
    registry = CapabilityRegistry()
    n = registry.register_default_tools(abilities)
    P(f"  Registry: {n} providers registered")
except Exception as e:
    P(f"  Registry: FAILED {e}")
    import traceback
    P(traceback.format_exc())

try:
    out = resolve_capabilities("Read this file", registry=registry,
        policy=abilities.policy, ability_manager=abilities, mode="deterministic")
    assert out.final == ["FILE_READ"], out.final
    P(f"  Deterministic resolve: PASSED -> {out.final}")
except Exception as e:
    P(f"  Deterministic resolve: FAILED {e}")
    import traceback
    P(traceback.format_exc())

try:
    ds = load_capability_dataset()
    P(f"  Dataset: {len(ds.get('cases', []))} cases loaded")
except Exception as e:
    P(f"  Dataset: FAILED {e}")
    import traceback
    P(traceback.format_exc())

P("\nDone.")
with open(r'c:\Users\hp\HERCULE\_quick_result.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(out_lines))
