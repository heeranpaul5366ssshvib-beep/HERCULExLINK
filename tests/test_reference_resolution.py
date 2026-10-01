from __future__ import annotations
"""Natural-language reference resolution tests (v1.1 upgrade layer).

Covers: file reference, previous-step output, "it", "that file",
"read it back", ambiguous, nonexistent, unverified output,
sandbox/traversal, multi-step chain, voice transcript, conversation
isolation. Uses the real resolver + real Brain pipeline (in-memory
stores); no microphone required.
"""

import os

import pytest

from cognition.planner.capable import build_capable_plan
from cognition.planner.references import (
    ReferenceResolutionError,
    extract_file_mentions,
    resolve_plan_references,
    resolve_step_texts,
    split_compound_steps,
)


def _plan(texts):
    return build_capable_plan("g", list(texts), chain=True)


# 1. file reference
def test_1_file_reference():
    resolved, report = resolve_step_texts(["Create test.py", "Read that file"])
    assert resolved[1] == "Read test.py"
    assert report["ok"] is True


# 2. previous-step output reference (file output)
def test_2_previous_step_output_reference():
    plan = _plan(["Create test.py", "Use the result"])
    resolved, report = resolve_plan_references(plan)
    assert report["ok"] is True
    assert "test.py" in resolved[1]["description"]


# 3. "it"
def test_3_it_resolves_to_single_candidate():
    resolved, _ = resolve_step_texts(["Create test.py", "Read it"])
    assert resolved[1] == "Read test.py"


# 4. "that file"
def test_4_that_file():
    plan = _plan(["Create test.py", "Open that file"])
    resolved, _ = resolve_plan_references(plan)
    assert "test.py" in resolved[1]["description"]
    assert "that file" not in resolved[1]["description"].lower()


# 5. "read it back"
def test_5_read_it_back():
    resolved, _ = resolve_step_texts(
        ["Create test.py with hello", "Read it back"])
    assert resolved[1] == "Read test.py back"


# 6. ambiguous reference (never guess, no execution)
def test_6_ambiguous_reference_lists_candidates():
    with pytest.raises(ReferenceResolutionError) as excinfo:
        resolve_step_texts(["Create a.py", "Create b.py", "Read it"])
    assert excinfo.value.code == "AMBIGUOUS_REFERENCE"
    assert set(excinfo.value.candidates) == {"a.py", "b.py"}


# 7. nonexistent reference
def test_7_nonexistent_reference():
    with pytest.raises(ReferenceResolutionError) as excinfo:
        resolve_step_texts(["Read it"])
    assert excinfo.value.code == "UNRESOLVED_REFERENCE"


# 8. reference to unverified output
def test_8_unverified_output_refused():
    with pytest.raises(ReferenceResolutionError) as excinfo:
        resolve_step_texts(
            ["Read it"],
            context={"unverified_artifacts": ["test.py"]})
    assert excinfo.value.code == "UNVERIFIED_REFERENCE"


# 9. sandbox / path traversal attempt
def test_9_traversal_reference_refused():
    with pytest.raises(ReferenceResolutionError) as excinfo:
        resolve_step_texts(
            ["Read it"],
            context={"verified_artifacts": ["../evil.txt"]})
    assert excinfo.value.code == "REFERENCE_SANDBOX_VIOLATION"


# 10. multi-step reference chain
def test_10_multi_step_chain():
    goal = "Create test.py, write a program in it, then read it back."
    from cognition.planner.capable import decompose_goal
    parts = decompose_goal(goal)
    split = split_compound_steps(parts)
    assert len(split) == 3
    resolved, _ = resolve_step_texts(split)
    assert resolved[0] == "Create test.py"
    assert "test.py" in resolved[1]
    assert "test.py" in resolved[2]
    plan = build_capable_plan(goal, resolved, chain=True)
    rplan, _ = resolve_plan_references(plan)
    assert all("test.py" in s["description"] for s in rplan)


# 11. voice transcript using references (same pipeline, no mic)
def test_11_voice_transcript_references(tmp_path, monkeypatch):
    os.environ.setdefault("HERCULE_TASK_STORE", ":memory:")
    os.environ.setdefault("HERCULE_ALLOW_MOCK", "1")
    os.environ.setdefault("HERCULE_DEFAULT_MODEL", "mock")
    # Hermetic world: ambient world entities must not join resolution.
    monkeypatch.setenv("HERCULE_WORLD_PATH", str(tmp_path / "world.json"))
    from runtime.initializer import RuntimeInitializer
    from interface.app_controller import HerculeAppController
    from voice.controller import VoiceController
    from voice.config import load_voice_config

    services = RuntimeInitializer().initialize()
    app = HerculeAppController(services)
    vc = VoiceController(app, config=load_voice_config(
        overrides={"enabled": True}))
    transcript = (
        'Create a file called voice_ref_test.py, write "HERCULE" into it, '
        "then read it back and verify it."
    )
    response = vc.submit_transcript(transcript)
    assert "COMPLETED" in response
    assert vc._last_result is not None
    assert vc._last_result.get("status") == "completed"
    assert vc._last_result.get("verification", {}).get("passed_steps") == 3
    # cleanup workspace artifact
    try:
        from abilities.files.file_ability import _workspace
        target = _workspace() / "voice_ref_test.py"
        if target.exists():
            target.unlink()
    except Exception:
        pass


# 12. normal conversation isolation (no references, no error)
def test_12_normal_conversation_untouched():
    resolved, report = resolve_step_texts(
        ["What is your name?", "Hi HERCULE"])
    assert resolved == ["What is your name?", "Hi HERCULE"]
    assert report["code"] == "NO_REFERENCES"
    assert extract_file_mentions("What is your name?") == []


# 12b. regression: determiner prose ("this topic") is not an anaphor.
# "Research this topic" must plan and complete, never fail with
# UNRESOLVED_REFERENCE (bare this/that before a content noun is prose).
def test_12b_determiner_prose_never_aborts_plan():
    plan = _plan(["Research this topic"])
    resolved, report = resolve_plan_references(plan)
    assert report["ok"] is True
    assert resolved[0]["description"] == "Research this topic"
    resolved_texts, report2 = resolve_step_texts(["Research this topic"])
    assert resolved_texts == ["Research this topic"]
    assert report2["code"] == "NO_REFERENCES"
    # Verb-less chatter ("it is raining") is likewise prose.
    resolved3, _ = resolve_step_texts(["it is raining today"])
    assert resolved3 == ["it is raining today"]
    # But true task anaphora still requires an antecedent.
    with pytest.raises(ReferenceResolutionError) as excinfo:
        resolve_step_texts(["run it"])
    assert excinfo.value.code == "UNRESOLVED_REFERENCE"
