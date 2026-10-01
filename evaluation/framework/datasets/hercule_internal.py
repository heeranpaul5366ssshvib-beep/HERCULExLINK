from __future__ import annotations
"""HERCULE-internal evaluations: architecture behaviors (Phase 3).

Probes hit frozen-core entry points directly and deterministically:

* request routing — ``boot.classify_request`` (the real deterministic
  router, no model call, same mechanism the UI/voice path uses);
* memory — ``MemoryManager.remember_fact`` / ``recall_fact`` store-
  then-recall and honest miss;
* planning contract — the model produces a JSON plan that is scored
  against the frozen capability-inference + verification gates;
* voice routing — same deterministic router on voice transcripts.

These are architecture probes: they measure HERCULE's wiring, not
model quality, so they never depend on model cleverness.
"""

from typing import Any, List

from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def _task(**kwargs) -> EvalTask:
    kwargs.setdefault("suite", "hercule_internal")
    kwargs.setdefault("category", EvalCategory.HERCULE_INTERNAL)
    kwargs.setdefault("safety_class", SafetyClass.READ_ONLY)
    kwargs.setdefault("evaluator", "contract scorer (routing/memory/planning)")
    kwargs.setdefault("timeout_s", 60.0)
    return EvalTask(**kwargs)


def _routing_probe(task_id: str, transcript: str, expected: str,
                   difficulty: str = "easy", style: str = "conversation routing") -> EvalTask:
    prompt = (f"Classify this request for HERCULE: '{transcript}'. "
              "Reply with one line only: routing: QUESTION, routing: GOAL or routing: MEMORY.")
    task = _task(
        task_id=task_id, prompt=prompt,
        expected_format="routing kind",
        scoring_method=ScoringMethod.ROUTING,
        expected=expected, difficulty=difficulty, style=style,
    )
    task.extras = {"classification": True, "transcript": transcript}
    return task


def hercule_internal_tasks() -> List[EvalTask]:
    return [
        # ---- conversation routing (question vs goal vs memory) ----
        _routing_probe("hercule-routing-question-001",
                       "What is the tallest mountain on Earth?", "QUESTION"),
        _routing_probe("hercule-routing-goal-002",
                       "Create a file called notes.txt with the word hello in it.", "GOAL"),
        _routing_probe("hercule-routing-memory-003",
                       "Remember that my favorite color is teal.", "MEMORY"),
        _routing_probe("hercule-routing-goal-004",
                       "calculate 25 * 4", "GOAL"),
        _routing_probe("hercule-voice-route-005",
                       "what do you remember about previous sessions", "MEMORY",
                       style="voice routing"),
        _routing_probe("hercule-voice-route-006",
                       "create a file called reminder.txt with the word tea in it",
                       "GOAL", style="voice routing"),

        # ---- memory persistence / retrieval (deterministic probes) ----
        _task(
            task_id="hercule-memory-persist-007",
            prompt=("Store then recall an evaluation fact through the MemoryManager "
                    "(executed deterministically by the runner)."),
            expected_format="recalled value",
            scoring_method=ScoringMethod.HONESTY,
            expected={"case": "known", "answers": ["eval-fact-verified-42"]},
            difficulty="easy", style="memory persistence",
            extras={"probe": "memory_probe", "operation": "store_then_recall",
                    "topic": "eval-fact-42", "value": "eval-fact-verified-42"},
        ),
        _task(
            task_id="hercule-memory-miss-008",
            prompt=("Recall a fact that was never stored; the memory probe must "
                    "return empty/unknown, never a fabricated value."),
            expected_format="value or UNKNOWN",
            scoring_method=ScoringMethod.HONESTY,
            expected={"case": "unknown"},
            difficulty="easy", style="memory retrieval honesty",
            extras={"probe": "memory_probe", "operation": "recall",
                    "topic": "eval-fact-that-never-existed-777"},
        ),

        # ---- planning contract (model-produced plan vs frozen gates) ----
        _task(
            task_id="hercule-plan-contract-009",
            prompt=("Produce a JSON plan (a list of steps) for: 'Create plan.txt, "
                    "write the word done into it, then read it back.' Each step must "
                    "be an object with keys description, required_capabilities and "
                    "verification_criteria. Return only the JSON, no prose."),
            expected_format="JSON plan list",
            scoring_method=ScoringMethod.CAPABILITY_GATED,
            expected=None,
            difficulty="hard", timeout_s=120.0, style="planning contract",
        ),
    ]
