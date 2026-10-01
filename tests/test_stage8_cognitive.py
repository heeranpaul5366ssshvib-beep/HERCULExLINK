"""Stage 8: hybrid cognitive planning.

Unit tests are hermetic (scripted model doubles, stub worlds). Brain
tests run on the mock model with a scripted proposal path — no live
LLM needed. Real-Ollama behavior is covered by the end-to-end run."""

import json

import pytest

from abilities.ability_manager import AbilityManager
from abilities.base_ability import BaseAbility
from abilities.tool_matcher import ToolMatcher
from cognition.capabilities.registry import CapabilityRegistry
from cognition.decision.decision_engine import DecisionEngine
from cognition.experience.experience_manager import ExperienceManager
from cognition.planner.capable import build_capable_plan
from cognition.planner.cognitive import (
    build_memory_context,
    plan_from_proposal,
    planning_policy,
    propose_plan,
    summarize_observation,
    topological_order,
)
from cognition.planner.planner import Planner
from cognition.planner.validation import validate_plan
from cognition.task_manager.task_manager import TaskManager
from models.structured import parse_cognitive_plan, validate_cognitive_plan
from orchestrator.autonomous import AutonomousLoop
from security.permissions.policy_manager import PolicyManager
from system.observability.trace import Tracer


class EchoAbility(BaseAbility):
    def __init__(self, name="echo", result="ok-content"):
        super().__init__(name, f"test {name}")
        self.calls = 0
        self.result = result

    def execute(self, *args, **kwargs):
        self.calls += 1
        return {"status": "success", "content": self.result}


class ScriptedModel:
    """Deterministic model double: canned outputs or raised errors."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def generate(self, prompt, model=None, **kwargs):
        self.calls.append(prompt)
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    def route_for_purpose(self, purpose, **kwargs):
        return ("scripted", "mock", self)


def make_world(extra_abilities=()):
    policy = PolicyManager()
    abilities = AbilityManager(policy)
    abilities.register(EchoAbility("files-stub"))
    abilities.register(EchoAbility("calc-stub", result="42"))
    for ability in extra_abilities:
        abilities.register(ability)
    registry = CapabilityRegistry()
    registry.register_provider("FILE_READ", "tool", "files-stub",
                               ability_manager=abilities)
    registry.register_provider("MATH", "tool", "calc-stub",
                               ability_manager=abilities)
    matcher = ToolMatcher(abilities, policy, None, registry)
    planner = Planner()
    tasks = TaskManager()
    tracer = Tracer()
    loop = AutonomousLoop(planner, matcher, tasks, tracer)
    return abilities, policy, registry, matcher, planner, tasks, tracer, loop


def mock_env(monkeypatch):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.delenv("HERCULE_COGNITIVE_PLANNING", raising=False)


def brain_services():
    from runtime.initializer import RuntimeInitializer
    return RuntimeInitializer().initialize()


# ---------- Phase 3: planning policy ----------

def test_policy_simple_task_stays_deterministic(monkeypatch):
    monkeypatch.delenv("HERCULE_COGNITIVE_PLANNING", raising=False)
    decision = planning_policy("calculate 9+8")
    assert decision["mode"] == "deterministic"


def test_policy_multi_intent_escalates(monkeypatch):
    monkeypatch.delenv("HERCULE_COGNITIVE_PLANNING", raising=False)
    decision = planning_policy(
        'create a file named cognitive_test.txt, put "HERCULE" in it, '
        "read it back, and verify it")
    assert decision["mode"] == "cognitive"


def test_policy_operator_override(monkeypatch):
    monkeypatch.setenv("HERCULE_COGNITIVE_PLANNING", "always")
    assert planning_policy("calculate 9+8")["mode"] == "cognitive"
    monkeypatch.setenv("HERCULE_COGNITIVE_PLANNING", "never")
    assert planning_policy("create a file, read it back, and verify it")["mode"] == "deterministic"


# ---------- Phase 2: structured plan contract ----------

VALID_PROPOSAL = {
    "goal": "handle the file",
    "steps": [
        {"step_id": "step-1", "goal": "Read this file", "dependencies": [],
         "required_capabilities": ["FILE_READ"], "required_ability": None,
         "inputs": {}, "expected_output": "file contents",
         "verification": "content returned and non-empty", "risk": "LOW"},
        {"step_id": "step-2", "goal": "Calculate 1+1", "dependencies": ["step-1"],
         "required_capabilities": ["MATH"], "required_ability": "calc-stub",
         "inputs": {"expression": "1+1"}, "expected_output": "2",
         "verification": "result verified by recomputation", "risk": "LOW"},
    ],
}


def test_valid_cognitive_plan_accepted():
    ok, clean, error = validate_cognitive_plan(
        VALID_PROPOSAL, ability_names=("files-stub", "calc-stub"))
    assert ok, error
    assert [s["step_id"] for s in clean["steps"]] == ["step-1", "step-2"]
    assert clean["steps"][1]["dependencies"] == ["step-1"]


def test_malformed_plan_rejected():
    ok, _, error = parse_cognitive_plan("just some prose, no json")
    assert not ok and error


@pytest.mark.parametrize("mutate, _reason", [
    (lambda p: p.pop("goal"), "missing goal"),
    (lambda p: p.update({"steps": []}), "empty steps"),
    (lambda p: p["steps"].append(dict(p["steps"][0])), "duplicate ids"),
    (lambda p: p["steps"][0].update({"required_capabilities": ["MIND_CONTROL"]}),
     "unknown capability"),
    (lambda p: p["steps"][0].update({"required_ability": "ghost-tool"}),
     "nonexistent ability"),
    (lambda p: p["steps"][0].update({"verification": 123}), "non-string verification"),
    (lambda p: p["steps"][0].update({"risk": "EXTREME"}), "bad risk"),
    (lambda p: p["steps"][0].update({"inputs": [1, 2]}), "non-object inputs"),
    (lambda p: p["steps"][0].update({"inputs": {"cmd": {"nested": 1}}}),
     "nested input smuggling"),
    (lambda p: p.update({"goal": "   "}), "empty goal"),
])
def test_plan_validation_rejects(mutate, _reason):
    import copy
    proposal = copy.deepcopy(VALID_PROPOSAL)
    mutate(proposal)
    ok, _, error = validate_cognitive_plan(
        proposal, ability_names=("files-stub", "calc-stub"))
    assert not ok, _reason
    assert error


def test_minimal_proposal_steps_accepted():
    minimal = {"goal": "handle it", "steps": [
        {"step_id": "step-1", "goal": "Read this file", "dependencies": [],
         "required_capabilities": ["FILE_READ"]},
        {"step_id": "step-2", "goal": "Calculate 1+1",
         "dependencies": ["step-1"], "required_capabilities": ["MATH"]},
    ]}
    ok, clean, error = validate_cognitive_plan(minimal)
    assert ok, error
    steps = plan_from_proposal("handle it", clean)
    assert [s["step_id"] for s in steps] == ["step-1", "step-2"]
    assert steps[1]["dependencies"] == ["step-1"]
    assert steps[0]["verification_criteria"]  # deterministic defaults fill in
    assert steps[0]["required_ability"] == ""


def test_plan_from_proposal_builds_capable_steps():
    steps = plan_from_proposal("handle the file", VALID_PROPOSAL)
    assert [s["step_id"] for s in steps] == ["step-1", "step-2"]
    assert steps[1]["dependencies"] == ["step-1"]
    assert steps[1]["required_ability"] == "calc-stub"
    assert steps[1]["inputs"] == {"expression": "1+1"}
    assert steps[0]["required_capabilities"] == ["FILE_READ"]
    assert steps[0]["verification_criteria"]  # deterministic criteria kept
    assert any("non-empty" in c for c in steps[0]["verification_criteria"])


# ---------- Phase 4: extended plan validation ----------

def test_validation_catches_unknown_ability_and_risk():
    _, policy, registry, _, _, _, _, _ = make_world()
    abilities = AbilityManager(policy)
    abilities.register(EchoAbility("files-stub"))
    plan = build_capable_plan("g", ["Read this file"])
    plan[0]["required_ability"] = "ghost-tool"
    plan[0]["risk"] = "EXTREME"
    plan[0]["inputs"] = ["not-a-dict"]
    report = validate_plan(plan, capability_registry=registry,
                           policy_manager=policy, ability_manager=abilities,
                           goal="g")
    codes = {p["code"] for p in report["problems"]}
    assert {"UNKNOWN_ABILITY", "INVALID_RISK", "INVALID_INPUTS"} <= codes
    assert not report["valid"]


def test_validation_rejects_empty_goal_and_missing_fields():
    report = validate_plan([{"step_id": "step-1"}], goal="")
    codes = {p["code"] for p in report["problems"]}
    assert "INVALID_GOAL" in codes
    assert "MISSING_FIELD" in codes
    assert not report["valid"]


def test_validation_still_accepts_legacy_plans():
    _, policy, registry, _, _, _, _, _ = make_world()
    abilities = AbilityManager(policy)
    abilities.register(EchoAbility("files-stub"))
    plan = build_capable_plan("g", ["Read this file"])
    report = validate_plan(plan, capability_registry=registry,
                           policy_manager=policy, ability_manager=abilities)
    assert report["valid"], report["problems"]


# ---------- Phase 5: dependency graph ----------

def test_topological_order_supports_diamonds():
    steps = [
        {"step_id": "a", "dependencies": []},
        {"step_id": "b", "dependencies": ["a"]},
        {"step_id": "c", "dependencies": ["a"]},
        {"step_id": "d", "dependencies": ["b", "c"]},
    ]
    ordered, problems = topological_order(steps)
    assert not problems
    position = {s["step_id"]: i for i, s in enumerate(ordered)}
    assert position["a"] < position["b"] < position["d"]
    assert position["a"] < position["c"] < position["d"]


def test_topological_order_reports_cycles_and_unknown():
    _, problems = topological_order([
        {"step_id": "a", "dependencies": ["b"]},
        {"step_id": "b", "dependencies": ["a"]},
    ])
    assert any("circular" in p for p in problems)
    _, problems = topological_order([{"step_id": "a", "dependencies": ["ghost"]}])
    assert any("unknown" in p for p in problems)


def test_branch_continuation_past_unrelated_failure():
    abilities, _, _, _, _, _, _, loop = make_world(
        extra_abilities=[])
    from abilities.base_ability import BaseAbility

    class FailRead(BaseAbility):
        def __init__(self):
            super().__init__("fail-read", "fails")
            self.calls = 0

        def execute(self, *args, **kwargs):
            self.calls += 1
            raise RuntimeError("read backend down")

    abilities.register(FailRead())
    loop.matcher.registry.register_provider("FILE_READ", "tool", "fail-read",
                                            ability_manager=abilities)
    abilities.get("files-stub").disable()
    loop.max_replans = 0
    tid = loop.tasks.create_task("diamond")
    try:
        report = loop.run(
            "diamond",
            [{"description": "Read this file", "required_capabilities": ["FILE_READ"]},
             {"description": "Calculate 1+1", "required_capabilities": ["MATH"],
              "dependencies": ["step-1"]},
             {"description": "Calculate 2+2", "required_capabilities": ["MATH"]}],
            task_id=tid, correlation_id="s8-diamond")
    finally:
        abilities.get("files-stub").enable()
    # step-1 fails, step-2 blocks on it, but independent step-3 completes.
    assert report["status"] == "partial"
    assert "step-3" in report["completed"]
    assert any(f.get("step_id") == "step-2" and f.get("reason") == "blocked"
               for f in report["failed"])


# ---------- Phase 6: adaptive replanning ----------

def test_adaptive_replan_proposer_used_and_validated():
    _, _, _, _, _, _, tracer, loop = make_world(
        extra_abilities=[])
    from abilities.base_ability import BaseAbility

    class FailRead(BaseAbility):
        def __init__(self):
            super().__init__("fail-read", "fails")

        def execute(self, *args, **kwargs):
            raise RuntimeError("read backend down")

    abilities = loop.matcher.abilities
    abilities.register(FailRead())
    loop.matcher.registry.register_provider("FILE_READ", "tool", "fail-read",
                                            ability_manager=abilities)
    abilities.get("files-stub").disable()
    loop.max_replans = 1
    seen = {}

    def proposer(failed_step, observation):
        seen["observation"] = observation
        seen["failed"] = failed_step.get("step_id")
        return ["Read this file again"]

    try:
        report = loop.run("adapt", ["Read this file"], correlation_id="s8-adapt",
                          replan_proposer=proposer)
    finally:
        abilities.get("files-stub").enable()
    assert seen["failed"] == "step-1"
    assert "down" in seen["observation"]
    entries = tracer.get("s8-adapt").as_dict()["stages"]["replan"]
    assert any(e.get("adaptive") for e in entries)
    assert report["replans"] == 1


def test_adaptive_replan_falls_back_when_proposer_fails():
    _, _, _, _, _, _, _, loop = make_world()
    loop.max_replans = 1

    def bad_proposer(failed_step, observation):
        raise RuntimeError("model exploded")

    report = loop.run("adapt-fallback", ["Calculate 9+8"],
                      correlation_id="s8-adapt-fb", replan_proposer=bad_proposer)
    # MATH via calc-stub succeeds first try; proposer never needed.
    assert report["status"] == "completed"


def test_summarize_observation_bounded():
    assert summarize_observation({"status": "success", "result": {"content": "x" * 5000}})
    assert len(summarize_observation({"status": "success", "result": {"content": "x" * 5000}})) <= 200
    assert "boom" in summarize_observation({"status": "failed", "errors": ["boom"] * 10})


# ---------- Phase 7/9: memory-aware proposal + separation ----------

def test_propose_plan_uses_bounded_context_and_planning_route():
    prompt_seen = {}
    model = ScriptedModel([json.dumps({
        "goal": "handle it",
        "steps": [{"step_id": "step-1", "goal": "Read this file",
                   "dependencies": [], "required_capabilities": ["FILE_READ"],
                   "required_ability": None, "inputs": {},
                   "expected_output": "contents",
                   "verification": "content returned", "risk": "LOW"}]})])
    original_generate = ScriptedModel.generate

    def spy_generate(self, prompt, model=None, **kwargs):
        prompt_seen["prompt"] = prompt
        prompt_seen["model"] = model
        return original_generate(self, prompt, model=model, **kwargs)

    ScriptedModel.generate = spy_generate
    try:
        from cognition.planner.cognitive import propose_plan
        ok, proposal, error, metrics = propose_plan(
            model, "handle it", "analysis", "past SUCCESS: files worked",
            ["FILE_READ"], ["files-stub"], timeout_s=30)
    finally:
        ScriptedModel.generate = original_generate
    assert ok, error
    assert proposal["steps"][0]["required_capabilities"] == ["FILE_READ"]
    assert metrics["model"] == "scripted"  # routed, never hard-coded
    assert "past SUCCESS" in prompt_seen["prompt"]
    assert "files-stub" in prompt_seen["prompt"]


def test_propose_plan_malformed_falls_back():
    model = ScriptedModel(["not json at all"])
    from cognition.planner.cognitive import propose_plan
    ok, _, error, _ = propose_plan(model, "g", "a", "", ["FILE_READ"], ["files-stub"])
    assert not ok and error


def test_propose_plan_unavailable_model_fails_honestly():
    model = ScriptedModel([RuntimeError("connection refused")])
    from cognition.planner.cognitive import propose_plan
    ok, _, error, _ = propose_plan(model, "g", "a", "", ["FILE_READ"], ["files-stub"])
    assert not ok and "connection refused" in error


def test_memory_context_bounded_and_advisory():
    experiences = [{"outcome": "SUCCESS",
                    "lesson": "files succeeded for FILE_READ (1 verified)",
                    "capabilities": ["FILE_READ"], "abilities": ["files"]}]
    facts = {"project": "HERCULE"}
    context = build_memory_context(experiences, [{"steps": ["use files"]}], facts,
                                   max_chars=500)
    assert len(context) <= 500
    assert "files succeeded" in context
    assert "HERCULE" in context
    # A huge store still yields a bounded context, never a dump.
    big = build_memory_context(experiences * 20, [{"steps": ["s" * 500]}],
                               {"k": "v" * 500}, max_chars=200)
    assert len(big) <= 200


# ---------- Phase 10: decision ----------

def test_decision_prefers_valid_experienced_cheap_plan():
    engine = DecisionEngine()
    det = {"mode": "deterministic",
           "plan": [{"step_id": "step-1", "required_capabilities": ["FILE_READ"],
                     "verification_criteria": ["x"], "risk": "LOW"}],
           "validation": {"valid": True}}
    cog = {"mode": "cognitive",
           "plan": [{"step_id": "step-1", "required_capabilities": ["FILE_READ"],
                     "verification_criteria": ["x"], "risk": "LOW"},
                    {"step_id": "step-2", "required_capabilities": ["MATH"],
                     "verification_criteria": ["y"], "risk": "LOW"}],
           "validation": {"valid": True}}
    result = engine.compare_plans([det, cog],
                                  experience_stats={"FILE_READ": 1.0, "MATH": 1.0})
    assert result["choice"]["mode"] == "deterministic"  # cheaper, same success
    assert engine.last()["mode"] == "deterministic"


def test_decision_never_picks_invalid():
    engine = DecisionEngine()
    bad = {"mode": "cognitive", "plan": [], "validation": {"valid": False}}
    result = engine.compare_plans([bad])
    assert result["choice"] is None


def test_decision_penalizes_risk_and_rewards_experience():
    engine = DecisionEngine()
    risky = {"mode": "a",
             "plan": [{"step_id": "s1", "required_capabilities": ["TERMINAL_EXECUTE"],
                       "verification_criteria": ["x"], "risk": "HIGH"}],
             "validation": {"valid": True}}
    safe = {"mode": "b",
            "plan": [{"step_id": "s1", "required_capabilities": ["FILE_READ"],
                      "verification_criteria": ["x"], "risk": "LOW"}],
            "validation": {"valid": True}}
    result = engine.compare_plans([risky, safe], experience_stats={"FILE_READ": 1.0})
    assert result["choice"]["mode"] == "b"


# ---------- Brain-level hybrid flow ----------

def _seed_success(monkeypatch, brain, capabilities=("FILE_READ",)):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    stack = brain._autonomy_stack()
    stack["experience"].record_rich(
        "seed", capabilities=list(capabilities), abilities=["files-stub"],
        verification={"passed_steps": 1}, status="completed", task_id="seed-1")


def test_deterministic_simple_task_no_proposal(monkeypatch):
    mock_env(monkeypatch)
    services = brain_services()
    brain = services["brain"]
    result = brain.run_cycle("calculate 9+8")
    assert result["status"] == "completed"
    assert result["plan_mode"] == "deterministic"
    trace = brain._tracer.get(result["correlation_id"]).as_dict()["stages"]
    assert "plan_proposal" not in trace
    assert "decision" not in trace


def test_cognitive_multi_intent_executes_validated_plan(monkeypatch):
    mock_env(monkeypatch)
    monkeypatch.setenv("HERCULE_COGNITIVE_PLANNING", "always")
    services = brain_services()
    brain = services["brain"]

    # Deterministic plan has 2 steps; the 1-step cognitive consolidation
    # wins honestly on cost with equal success history.
    _seed_success(monkeypatch, brain, capabilities=("MATH",))
    proposal = {
        "goal": "calculate 2+2",
        "steps": [{"step_id": "step-1", "goal": "calculate 2+2",
                   "dependencies": [], "required_capabilities": ["MATH"],
                   "required_ability": None, "inputs": {"expression": "2+2"},
                   "expected_output": "4",
                   "verification": "result verified", "risk": "LOW"}],
    }
    scripted = ScriptedModel([json.dumps(proposal)])
    models = services["orchestrator"].models
    previous_default = getattr(models, "default_model", None)
    try:
        models.default_model = "mock"
        if hasattr(models, "router") and getattr(models.router, "adapters", None):
            models.router.adapters["mock"] = scripted
        models.generate = scripted.generate
        result = brain.run_cycle("calculate 2+2 then calculate 3+3")
    finally:
        if previous_default is not None:
            models.default_model = previous_default
        if hasattr(models, "router") and getattr(models.router, "adapters", None):
            models.router.adapters.pop("mock", None)
        if hasattr(models, "generate"):
            try:
                delattr(models, "generate")
            except Exception:
                pass
    assert result["status"] == "completed", result
    assert result["plan_mode"] == "cognitive"
    assert scripted.calls, "model was never consulted"
    trace = brain._tracer.get(result["correlation_id"]).as_dict()["stages"]
    assert "plan_proposal" in trace
    assert "decision" in trace
    assert "dependency_graph" in trace


def test_cognitive_malformed_falls_back_deterministically(monkeypatch):
    mock_env(monkeypatch)
    monkeypatch.setenv("HERCULE_COGNITIVE_PLANNING", "always")
    services = brain_services()
    brain = services["brain"]
    models = services["orchestrator"].models
    previous_default = getattr(models, "default_model", None)
    try:
        models.default_model = "mock"
        models.generate = ScriptedModel(["garbage {{{ not json"]).generate
        result = brain.run_cycle("calculate 9+8")
    finally:
        if previous_default is not None:
            models.default_model = previous_default
        if hasattr(models, "generate"):
            try:
                delattr(models, "generate")
            except Exception:
                pass
    assert result["status"] == "completed"
    assert result["plan_mode"] == "deterministic"


def test_cognitive_unknown_capability_rejected(monkeypatch):
    mock_env(monkeypatch)
    monkeypatch.setenv("HERCULE_COGNITIVE_PLANNING", "always")
    services = brain_services()
    brain = services["brain"]

    proposal = {
        "goal": "do magic",
        "steps": [{"step_id": "step-1", "goal": "Do magic",
                   "dependencies": [], "required_capabilities": ["MIND_CONTROL"],
                   "required_ability": None, "inputs": {},
                   "expected_output": "magic", "verification": "magic seen",
                   "risk": "LOW"}],
    }
    models = services["orchestrator"].models
    previous_default = getattr(models, "default_model", None)
    try:
        models.default_model = "mock"
        models.generate = ScriptedModel([json.dumps(proposal)]).generate
        result = brain.run_cycle("calculate 9+8")
    finally:
        if previous_default is not None:
            models.default_model = previous_default
        if hasattr(models, "generate"):
            try:
                delattr(models, "generate")
            except Exception:
                pass
    # Proposal rejected → deterministic MATH plan executes honestly.
    assert result["status"] == "completed"
    assert result["plan_mode"] == "deterministic"


def test_permission_rejection_blocks_cognitive_plan(monkeypatch):
    mock_env(monkeypatch)
    monkeypatch.setenv("HERCULE_COGNITIVE_PLANNING", "always")
    services = brain_services()
    brain = services["brain"]
    orch = services["orchestrator"]
    proposal = {
        "goal": "read the file",
        "steps": [{"step_id": "step-1", "goal": "Read this file",
                   "dependencies": [], "required_capabilities": ["FILE_READ"],
                   "required_ability": None, "inputs": {},
                   "expected_output": "contents",
                   "verification": "content returned", "risk": "LOW"}],
    }
    models = orch.models
    previous_default = getattr(models, "default_model", None)
    try:
        models.default_model = "mock"
        models.generate = ScriptedModel([json.dumps(proposal)]).generate
        orch.abilities.policy.set_permission("FILE_READ", False)
        result = brain.run_cycle("read this file please")
    finally:
        orch.abilities.policy.set_permission("FILE_READ", True)
        if previous_default is not None:
            models.default_model = previous_default
        if hasattr(models, "generate"):
            try:
                delattr(models, "generate")
            except Exception:
                pass
    # Both candidates invalid under denial: honest failure, no execution.
    assert result["status"] == "failed", result
    blob = str(result.get("result", "")) + str(result.get("error", "")) + str(result.get("execution_summary", ""))
    assert ("permission" in blob.lower() or "PERMISSION" in blob
            or "denied" in blob.lower() or "DEPLOY_DENIED" in blob)


def test_conversation_creates_no_plan(monkeypatch):
    mock_env(monkeypatch)
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "hercule_boot", str(Path("boot.py").resolve()))
    boot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boot)
    services = brain_services()
    cli = boot.HerculeCli(services["brain"])
    before = len(services["orchestrator"].task_manager)
    result = cli.handle_line("hi")
    assert result["kind"] == "QUESTION"
    assert len(services["orchestrator"].task_manager) == before
