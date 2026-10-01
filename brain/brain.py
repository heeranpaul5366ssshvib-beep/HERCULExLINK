from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Brain
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from brain.consciousness import Consciousness
from brain.intelligence import Intelligence
from brain.goal_manager import GoalManager
from brain.planner import Planner as LegacyPlanner
from brain.reasoning_engine import ReasoningEngine as LegacyReasoningEngine
from brain.decision_engine import DecisionEngine as LegacyDecisionEngine
from brain.learning_engine import LearningEngine
from brain.reflection_engine import ReflectionEngine

from cognition.planner.planner import Planner as CanonicalPlanner
from cognition.reasoning.reasoner import Reasoner
from cognition.decision.decision_engine import DecisionEngine as CanonicalDecisionEngine


class Brain:
    """
    ==========================================
                HERCULE BRAIN
    ==========================================

    Executive AI Controller

    Responsible for

    • Consciousness
    • Intelligence
    • Goals
    • Planning
    • Reasoning
    • Decision Making
    • Learning
    • Reflection

    Coordinates the Orchestrator and
    every major subsystem.

    Future

    • Autonomous Thinking
    • Multi-Agent Collaboration
    • Recursive Self Improvement
    • Long-Term Planning
    • Emotional Intelligence
    • Meta Reasoning
    • World Model
    • Self Awareness
    """

    def __init__(

        self,

        orchestrator,

    ):

        self.event_bus = getattr(orchestrator, "event_bus", None)
        self.canonical_execution_path = [
            "INTENT",
            "CONTEXT",
            "MEMORY / KNOWLEDGE",
            "BRAIN",
            "REASONING",
            "GOAL / PLAN",
            "DECISION",
            "ORCHESTRATOR",
            "TASK MANAGER",
            "POLICY",
            "TOOL / AGENT",
            "EXECUTION",
            "OBSERVATION",
            "VERIFICATION",
            "REFLECTION",
            "MEMORY / EXPERIENCE",
            "RESPONSE",
        ]

        self.orchestrator = orchestrator

        self.consciousness = Consciousness()

        self.intelligence = Intelligence()

        self.goals = GoalManager()

        self.authoritative_planner = CanonicalPlanner()
        self.authoritative_reasoner = Reasoner(getattr(orchestrator, "models", None))
        self.authoritative_decision = CanonicalDecisionEngine()

        self.planner = self.authoritative_planner
        self.planner.create = lambda goal, *args, **kwargs: self.authoritative_planner.create_plan(goal, [str(goal)])
        self.planner.reset = self.authoritative_planner.clear
        self.reasoning = LegacyReasoningEngine()
        self.decision = self.authoritative_decision

        self.learning = LearningEngine()

        self.reflection = ReflectionEngine()

        # World model (v2, additive context only): structured current
        # state. Never permission authority; never breaks Brain when
        # its store is unavailable.
        try:
            from world.model import WorldModel

            self.world = WorldModel()
        except Exception:
            self.world = None
        # Last adaptive reasoning decision (observability only).
        self.last_reasoning = {}
        # Last Phase-5 strategy decision (observability only; §15).
        self.last_decision: dict = {}

        self.running = False
        # NOTE: legacy direct-execution pipeline stages (_reason_stage /
        # _plan_stage / _execute_stage / _memory_stage) are intentionally
        # NOT auto-registered. They bypass TaskManager/Policy/Verification
        # and conflict with the canonical run_cycle -> AutonomousLoop path.
        # They remain as deprecated methods for backwards compatibility only.

    ##################################################
    # LIFECYCLE
    ##################################################

    def start(self):

        self.running = True

        self.consciousness.set_state(

            "ACTIVE",

        )

    ##################################################

    def stop(self):

        self.running = False

        self.consciousness.set_state(

            "IDLE",

        )

    ##################################################
    # GOALS
    ##################################################

    def set_goal(

        self,

        goal,

    ):

        self.goals.add_goal(

            goal,

        )

        self.consciousness.focus_on(

            goal,

        )

    ##################################################

    def current_goal(self):

        goals = self.goals.active_goals()

        if not goals:

            return None

        return goals[0]

    ##################################################
    # THINK (conversation path — no tasks, no planning, no healing)
    ##################################################

    def think(

        self,

        prompt,

    ):

        """Clean reasoning/conversation path.

        Uses the model only. Never creates tasks, plans, capability
        resolution, tool execution, or self-healing. Consciousness moves
        ACTIVE -> THINKING -> ACTIVE (or ERROR on failure). Failures are
        structured: subsystem/operation/exception/recovery/result.
        """
        import logging as _logging
        import time as _time

        _log = _logging.getLogger("HERCULE.RequestLifecycle")
        started = _time.perf_counter()
        text = str(prompt or "")
        _log.info("BRAIN think REQUEST input=[%.80s]", text)
        try:
            self.consciousness.transition("THINKING", f"think:{text[:60]}")
        except Exception:
            pass
        try:
            self.consciousness.focus_on(text[:200])
            # MEMORY RETRIEVAL → CONTEXT: bounded relevant facts only.
            memory_context = ""
            try:
                memory = getattr(self.orchestrator, "memory", None)
                if memory is not None and hasattr(memory, "search_memory"):
                    hits = memory.search_memory(text, memory_type="semantic", limit=3) or []
                    lines = [str(h.get("record", {}).get("content", ""))[:160]
                             for h in hits if h.get("record", {}).get("content")]
                    memory_context = "\n".join(lines)[:500]
                    _log.info("MEMORY_RETRIEVAL→CONTEXT matches=%d", len(lines))
            except Exception:
                memory_context = ""
            # WORLD MODEL → CONTEXT (v2): bounded relevant current-state
            # slice alongside memory. Failures fall back to memory only.
            world_context = ""
            try:
                world_context = self.world_context(text)
            except Exception:
                world_context = ""
            memory_fallback = "\n".join(
                part for part in (memory_context, world_context) if part)[:1000]
            # LAYERED BRAIN CONTEXT (v2): request + world + relevant
            # memories + experience + task state, all bounded.
            try:
                combined_context = self.build_brain_context(text) or memory_fallback
            except Exception:
                combined_context = memory_fallback
            # Adaptive budget (v2 Phase 4): conversational requests use
            # the LIGHT model/budget; never changes what is authorized.
            call_kwargs: dict = {}
            try:
                _decision = self.decide_reasoning(text, is_question=True)
                if _decision.get("model"):
                    call_kwargs["model"] = _decision["model"]
                _budget = _decision.get("budget", {}) or {}
                if int(_budget.get("max_tokens", 0) or 0) > 0:
                    call_kwargs["options"] = {"num_predict": int(_budget["max_tokens"])}
            except Exception:
                call_kwargs = {}
            answer = self.orchestrator.agent.think(text, memory=combined_context,
                                                  **call_kwargs)
        except Exception as exc:
            try:
                self.consciousness.set_state("ERROR", f"think failed: {exc}")
            except Exception:
                pass
            err = (f"[HERCULE Error]: subsystem='brain' operation='think' "
                   f"exception='{exc}' recovery='none' result='failed'")
            _log.error("BRAIN think FAILED error=[%.160s]", err)
            try:
                self.consciousness.set_state("ACTIVE", "think-error-recovered")
            except Exception:
                pass
            return err
        if isinstance(answer, str) and "dynamically synthesized" in answer:
            # Honest guard: a fabricated fallback must never surface as chat.
            err = ("[HERCULE Error]: subsystem='models' operation='generate' "
                   "exception='synthesized fallback detected' recovery='none' "
                   "result='failed'")
            _log.error("BRAIN think FAILED error=[synthesized fallback detected]")
            try:
                self.consciousness.set_state("ERROR", "synthesized fallback")
                self.consciousness.set_state("ACTIVE", "think-error-recovered")
            except Exception:
                pass
            return err
        latency_ms = round((_time.perf_counter() - started) * 1000.0, 2)
        _log.info("BRAIN think RESPONSE latency_ms=%.2f", latency_ms)
        # Conversational memory: best-effort episodic record, never fatal.
        try:
            memory = getattr(self.orchestrator, "memory", None)
            if memory is not None and hasattr(memory, "remember_event"):
                memory.remember_event({"kind": "conversation", "prompt": text[:500],
                                       "response": str(answer)[:500]})
        except Exception:
            pass
        try:
            self.consciousness.set_state("ACTIVE", "think complete")
        except Exception:
            pass
        return answer

    ##################################################
    # FULL PIPELINE (CANONICAL: AutonomousLoop)
    ##################################################

    def _emit_event(self, event: str, **payload) -> None:
        """Publish a lifecycle event on the orchestrator's EventBus (UAI §29).

        Best-effort: observability never breaks the request pipeline.
        Handlers receive keyword args only; exceptions are swallowed.
        """
        bus = getattr(self, "event_bus", None)
        if bus is None:
            return
        try:
            bus.publish(event, **payload)
        except Exception:
            pass

    def run_cycle(self, prompt: str, steps=None, task_id: str = "",
                  correlation_id: str = "", payload_fn=None,
                  use_semantic=None, semantic_proposer=None):
        """Run the canonical goal -> autonomous execution path.

        INPUT → INTENT → CONTEXT → MEMORY/KNOWLEDGE → BRAIN → REASONING →
        GOAL → PLAN → CAPABILITY RESOLUTION → TOOL MATCHING → POLICY →
        EXECUTION → OBSERVATION → VERIFICATION → REFLECTION → MEMORY →
        RESPONSE.

        The Brain never executes tools directly; the verified
        AutonomousLoop (composed, not duplicated) is the sole live
        execution mechanism. Returns a structured result contract —
        never private reasoning traces, never fabricated success.

        Consciousness transitions: PLANNING → EXECUTING → VERIFYING →
        REFLECTING → ACTIVE (or ERROR → RECOVERING on failure).
        ``use_semantic``/``semantic_proposer`` select hybrid capability
        resolution for this run (planner default otherwise); replans
        inherit the same setting for consistency.
        """
        import logging as _logging
        import time
        import uuid

        _log = _logging.getLogger("HERCULE.RequestLifecycle")
        started = time.perf_counter()
        correlation_id = correlation_id or f"brain-{uuid.uuid4().hex[:12]}"
        goal = str(prompt)
        _log.info("[%s] REQUEST input=[%.120s]", correlation_id, goal)
        self._emit_event("USER_REQUEST", correlation_id=correlation_id, goal=goal[:200])
        try:
            self.consciousness.transition("UNDERSTANDING", f"run_cycle:{goal[:60]}")
        except Exception:
            pass
        self.consciousness.focus_on(goal[:200])
        # Goal lifecycle (Phase 7): track queued → active → terminal.
        goal_id = ""
        try:
            goal_id = self.goals.add(goal[:200], metadata={"correlation_id": correlation_id})
            self.goals.activate(goal_id)
            self._emit_event("GOAL_CREATED", correlation_id=correlation_id,
                             goal_id=goal_id, goal=goal[:200])
        except Exception:
            pass

        def _fail_goal(reason=""):
            try:
                if goal_id:
                    self.goals.fail(goal_id, reason)
            except Exception:
                pass

        try:
            stack = self._autonomy_stack()
        except Exception as exc:
            _fail_goal("compose-stack")
            return self._autonomy_failure(
                goal, task_id, correlation_id, started,
                subsystem="brain", operation="compose-stack", exception=exc)

        self._trace(correlation_id, "request", {"prompt": goal[:200]})
        self._trace(correlation_id, "intent", {"goal": goal[:200]})
        _log.info("[%s] INTENT→CONTEXT goal=[%.80s]", correlation_id, goal)

        # MEMORY / KNOWLEDGE context (best-effort, never fatal).
        try:
            self._trace(correlation_id, "context", {"goal": goal[:200]})
            _log.info("[%s] MEMORY/KNOWLEDGE context-attached", correlation_id)
        except Exception:
            pass

        try:
            self.consciousness.transition("REASONING", f"reason:{goal[:60]}")
        except Exception:
            pass
        # Adaptive reasoning (v2 Phase 4): the controller decides how
        # much reasoning this goal deserves BEFORE any model call, so
        # simple deterministic tasks skip the model entirely (v1.0 fast
        # path preserved byte-identically). Explicit semantic flags
        # still force the model path as before.
        from cognition.planner.cognitive import planning_policy as _planning_policy
        _policy_early = _planning_policy(goal)
        _reasoning_decision = self.decide_reasoning(goal)
        try:
            self._trace(correlation_id, "reasoning_decision",
                        {"mode": _reasoning_decision.get("mode", ""),
                         "model": str(_reasoning_decision.get("model", ""))[:80],
                         "risk": _reasoning_decision.get("risk", ""),
                         "complexity": _reasoning_decision.get("complexity", 0)})
        except Exception:
            pass
        _needs_model_reasoning = (
            _reasoning_decision.get("mode", "STANDARD") != "DETERMINISTIC"
            or _policy_early.get("mode") == "cognitive"
            or use_semantic is not None or semantic_proposer is not None)
        try:
            if _needs_model_reasoning:
                _budgeted = self.reason_with_decision(prompt, _reasoning_decision)
                reasoning = _budgeted.get("summary", "") if isinstance(_budgeted, dict) else _budgeted
                if isinstance(_budgeted, dict) and _budgeted.get("status") == "failed":
                    raise RuntimeError(str(_budgeted.get("error", "reasoning failed"))[:300])
                if not str(reasoning or "").strip():
                    reasoning = self.reason(prompt)
            else:
                reasoning = self.reasoning.reason(prompt)
        except Exception as exc:
            _fail_goal("reasoning")
            return self._autonomy_failure(
                goal, task_id, correlation_id, started,
                subsystem="brain",
                operation="reasoning", exception=exc)
        reasoning_summary = (str(reasoning)[:200]
                             if not isinstance(reasoning, dict) else "structured")
        self._trace(correlation_id, "reasoning",
                    {"summary": reasoning_summary,
                     "llm_skipped": not _needs_model_reasoning})
        self._trace(correlation_id, "cognitive_analysis",
                    {"summary": reasoning_summary})
        _log.info("[%s] BRAIN→REASONING done", correlation_id)

        # MEMORY RETRIEVAL (Stage 5/8): relevant past experiences inform
        # planning/ability selection. Summaries only — never CoT.
        try:
            self.consciousness.transition("RECALLING", f"recall:{goal[:60]}")
        except Exception:
            pass
        preferred: dict = {}
        relevant: list = []
        planner_context = ""
        try:
            relevant = self.relevant_experiences(goal, limit=3)
            self._trace(correlation_id, "memory_retrieval",
                        {"matches": len(relevant),
                         "lessons": [e.get("lesson", "")[:160] for e in relevant]})
            _log.info("[%s] MEMORY_RETRIEVAL matches=%d", correlation_id, len(relevant))
            for entry in relevant:
                if entry.get("outcome") not in ("SUCCESS", "RECOVERED"):
                    continue
                for cap, ability in zip(entry.get("capabilities", []) or [],
                                        entry.get("abilities", []) or []):
                    preferred.setdefault(str(cap).upper(), str(ability))
            planner_context = self._planner_memory_context(goal, relevant)
        except Exception:
            preferred = {}

        try:
            self.consciousness.transition("PLANNING", f"plan:{goal[:60]}")
        except Exception:
            pass
        self._emit_event("PLAN_STARTED", correlation_id=correlation_id, goal=goal[:200])
        # ANALYZE (Phase 2): decompose multi-action goals deterministically;
        # explicit steps or single-action goals pass through unchanged.
        decomposed = False
        try:
            from cognition.planner.capable import decompose_goal
            if steps is None:
                step_texts = decompose_goal(goal)
                decomposed = len(step_texts) > 1
            else:
                step_texts = list(steps)
        except Exception:
            step_texts = list(steps) if steps else [goal]
        # v1.1 upgrade layer: split comma-joined multi-action steps
        # ("Create test.py, write ... into it, then ...") into ordered
        # atomic steps, then resolve anaphoric references ("it", "that
        # file", "read it back") BEFORE the plan contract gate. This
        # changes wording only; validation/capability/policy gates below
        # still judge the executable plan unchanged.
        if steps is None:
            try:
                from cognition.planner.references import split_compound_steps
                refined = split_compound_steps([str(s) if isinstance(s, str) else s for s in step_texts])
                # split_compound_steps only handles strings; preserve any
                # non-string caller steps verbatim (none in this branch).
                if all(isinstance(s, str) for s in step_texts):
                    step_texts = refined
                    decomposed = len(step_texts) > 1
            except Exception:
                pass
        try:
            from cognition.planner.references import resolve_step_texts
            _str_only = all(isinstance(s, str) for s in step_texts)
            if _str_only:
                _ref_ctx = {"world": getattr(self, "world", None)}
                step_texts, _ref_pre = resolve_step_texts([str(s) for s in step_texts],
                                                          context=_ref_ctx)
                if _ref_pre.get("resolutions"):
                    self._trace(correlation_id, "reference_resolution",
                                {"stage": "pre-plan", "resolutions": _ref_pre.get("resolutions")})
        except Exception as exc:
            try:
                from cognition.planner.references import ReferenceResolutionError
                if isinstance(exc, ReferenceResolutionError):
                    self._trace(correlation_id, "reference_resolution",
                                {"ok": False, **exc.as_dict()})
                    _fail_goal("reference-resolution")
                    return self._failure_result(
                        goal, "failed",
                        f"subsystem='planner' operation='reference-resolution' "
                        f"exception='{exc.code} {exc.detail} candidates={exc.candidates}' "
                        f"recovery='clarify' result='failed'",
                        correlation_id, started, task_id=task_id,
                        reasoning=self._reasoning_public(_reasoning_decision))
            except Exception:
                pass
            # Non-reference errors: fall through to normal planning so a
            # resolver bug can never break the frozen deterministic path.
            pass
        self._trace(correlation_id, "goal",
                    {"goal": goal[:200], "goal_id": goal_id,
                     "decomposed_steps": len(step_texts)})
        try:
            plan, plan_mode, plan_info = self.plan_with_policy(
                goal, step_texts, decomposed, reasoning_summary,
                planner_context, correlation_id,
                semantic=use_semantic, proposer=semantic_proposer,
                allow_skills=(steps is None))
        except Exception as exc:
            _fail_goal("create-plan")
            return self._autonomy_failure(
                goal, task_id, correlation_id, started,
                subsystem="planner", operation="create-plan", exception=exc)
        if plan_info.get("decision"):
            self._trace(correlation_id, "decision", plan_info["decision"])
            # Phase 5 observability (§15/§16): last decision exposed for the
            # read-only UI panel/HUD. Structured reasons only, never CoT.
            self.last_decision = dict(plan_info["decision"])
        self._emit_event("PLAN_CREATED", correlation_id=correlation_id,
                         goal_id=goal_id, plan_mode=plan_mode,
                         steps=[s.get("step_id") for s in plan])
        _log.info("[%s] PLAN mode=%s steps=%s", correlation_id, plan_mode,
                  [s.get("step_id") for s in plan])
        # v1.1: REFERENCE RESOLUTION sits between PLAN and PLAN VALIDATION.
        # Rewrites anaphoric step wording ("it", "that file", "read it
        # back") to explicit verified artifacts when unambiguous; ambiguous
        # / unresolved / unverified / sandbox-escaping references abort
        # BEFORE validation/execution with a structured clarification error.
        try:
            from cognition.planner.references import resolve_plan_references
            plan, _ref_report = resolve_plan_references(
                plan, context={"world": getattr(self, "world", None)})
            if _ref_report.get("resolutions"):
                self._trace(correlation_id, "reference_resolution",
                            {"stage": "post-plan", "resolutions": _ref_report.get("resolutions")})
                _log.info("[%s] REFERENCE_RESOLUTION resolved=%d", correlation_id,
                          len(_ref_report.get("resolutions") or []))
                # Resolved wording may carry new capabilities; loop_steps
                # below rebuilds from step_texts for deterministic mode, so
                # keep step_texts in sync for the executable path.
                try:
                    if plan_mode != "cognitive":
                        step_texts = [str(s.get("description", "")) for s in plan]
                except Exception:
                    pass
        except Exception as exc:
            try:
                from cognition.planner.references import ReferenceResolutionError
                if isinstance(exc, ReferenceResolutionError):
                    self._trace(correlation_id, "reference_resolution",
                                {"ok": False, **exc.as_dict()})
                    try:
                        self.consciousness.set_state("ERROR", f"reference {exc.code}")
                        self.consciousness.set_state("IDLE", "reference failure")
                    except Exception:
                        pass
                    _fail_goal("reference-resolution")
                    return self._failure_result(
                        goal, "failed",
                        f"subsystem='planner' operation='reference-resolution' "
                        f"exception='{exc.code} {exc.detail} candidates={exc.candidates}' "
                        f"recovery='clarify' result='failed'",
                        correlation_id, started, task_id=task_id,
                        reasoning=self._reasoning_public(_reasoning_decision))
            except Exception:
                pass
            pass
        # Planner contract: every executable step needs step_id, goal/
        # objective, required_capabilities, verification_criteria.
        contract_problems = self._plan_contract_problems(plan)
        if contract_problems:
            self._trace(correlation_id, "plan", {"contract_problems": contract_problems})
            _log.error("[%s] PLAN contract-invalid problems=%s", correlation_id, contract_problems)
            try:
                self.consciousness.set_state("ERROR", "plan contract invalid")
                self.consciousness.set_state("IDLE", "contract failure")
            except Exception:
                pass
            _fail_goal("plan-contract")
            return self._failure_result(
                goal, "failed",
                f"subsystem='planner' operation='plan-contract' "
                f"exception='{contract_problems}' recovery='none' result='failed'",
                correlation_id, started, task_id=task_id,
                reasoning=self._reasoning_public(_reasoning_decision))
        self._trace(correlation_id, "plan",
                    {"steps": [s.get("step_id") for s in plan],
                     "capabilities": sorted({c for s in plan for c in s.get("required_capabilities", [])})})
        _log.info("[%s] PLAN steps=%s capabilities=%s", correlation_id,
                  [s.get("step_id") for s in plan],
                  sorted({c for s in plan for c in s.get("required_capabilities", [])}))
        try:
            self.consciousness.transition("EXECUTING", f"executing:{goal[:60]}")
        except Exception:
            pass

        tasks = stack["tasks"]
        try:
            if task_id:
                task = tasks.get(task_id)
                if str(task.get("status", "")).upper() == "COMPLETED":
                    cached = (task.get("metadata", {}) or {}).get("autonomy_report")
                    if cached:
                        try:
                            self.consciousness.set_state("ACTIVE", "idempotent replay")
                        except Exception:
                            pass
                        return {**cached, "task_id": task_id, "correlation_id": correlation_id,
                                "idempotent": True}
                current = str(task.get("status", "")).upper()
                if current in ("RUNNING", "QUEUED") and self._task_in_flight(tasks, task_id):
                    # A step is marked running with no outcome: another
                    # attempt may own it — report, never double-execute.
                    # All other non-terminal states are adopted as resume.
                    try:
                        self.consciousness.set_state("WAITING", f"waiting:{task_id}")
                    except Exception:
                        pass
                    return {"task_id": task_id, "status": "in-progress",
                            "result": {}, "verification": {},
                            "retries": self._retry_count(tasks, task_id),
                            "execution_summary": f"task already {current.lower()}",
                            "correlation_id": correlation_id, "latency_ms": 0.0}
                if current == "PAUSED":
                    self._resume_quietly(tasks, task_id)
            else:
                task_id = tasks.create_task(goal, metadata={"correlation_id": correlation_id, "goal": goal})
            self._trace(correlation_id, "task_creation", {"task_id": task_id})
            self._advance_quietly(tasks, task_id, "queue")
            self._advance_quietly(tasks, task_id, "start")
        except Exception as exc:
            _fail_goal("create-task")
            return self._autonomy_failure(
                goal, task_id, correlation_id, started,
                subsystem="task-manager", operation="create-task", exception=exc)

        # Safe resume: tasks with prior progress re-enter through the
        # resume planner (SKIP/REPLAY/COMPENSATE/BLOCK) before the loop.
        if self._task_has_progress(tasks, task_id):
            blocked = self._resume_task(stack, tasks, task_id, plan, correlation_id)
            if blocked is not None:
                try:
                    self.consciousness.set_state("ERROR", "resume blocked")
                except Exception:
                    pass
                _fail_goal("resume-blocked")
                return blocked

        try:
            _log.info("[%s] CAPABILITY→TOOL→POLICY→EXECUTION task=%s", correlation_id, task_id)
            replan_proposer = None
            if plan_mode == "cognitive":
                try:
                    replan_proposer = self._cognitive_replan_fn(
                        goal, planner_context, correlation_id)
                except Exception:
                    replan_proposer = None
            # Cognitive winners travel as dict steps so dependencies,
            # ability hints, inputs, and verification survive the loop's
            # rebuild (dict fields are preserved, then re-validated).
            # Sequential chaining applies only to deterministic text steps.
            # Adopted skill procedures travel as the loop's steps so the
            # executed plan is the skill procedure (still re-validated,
            # matched, authorized, and verified inside the loop).
            skill_proc = (plan_info.get("skill") or {}).get("procedure") or []
            if plan_mode == "cognitive":
                loop_steps, loop_chain = plan, False
            elif skill_proc:
                loop_steps, loop_chain = list(skill_proc), False
            else:
                loop_steps, loop_chain = step_texts, decomposed
            report = stack["loop"].run(goal, loop_steps, task_id=task_id,
                                       correlation_id=correlation_id, payload_fn=payload_fn,
                                       semantic=use_semantic, semantic_proposer=semantic_proposer,
                                       preferred=preferred or None,
                                       chain=loop_chain,
                                       replan_proposer=replan_proposer)
        except Exception as exc:
            try:
                tasks.fail(task_id, str(exc)[:300])
            except Exception:
                pass
            _fail_goal("execute")
            return self._autonomy_failure(
                goal, task_id, correlation_id, started,
                subsystem="autonomous-loop", operation="execute", exception=exc)
        try:
            self.consciousness.transition("OBSERVING", f"observing:{task_id}")
        except Exception:
            pass
        self._trace(correlation_id, "observation",
                    {"task_id": task_id, "completed": report.get("completed", []),
                     "failed": [f.get("step_id", "") if isinstance(f, dict) else str(f)[:60]
                                for f in report.get("failed", []) or []]})
        self._emit_event("OBSERVATION_RECEIVED", correlation_id=correlation_id,
                         task_id=task_id,
                         completed=list(report.get("completed", [])))
        try:
            self.consciousness.transition("VERIFYING", f"verifying:{task_id}")
        except Exception:
            pass
        _log.info("[%s] OBSERVATION→VERIFICATION status=%s", correlation_id, report.get("status"))

        status = str(report.get("status", "failed"))
        summary = {"completed": report.get("completed", []), "failed": report.get("failed", []),
                   "replans": report.get("replans", 0)}
        # Honest failure detail: surface failed-step reasons, never bare {}.
        failure_detail = ""
        if status not in ("completed", "partial"):
            parts = []
            for item in report.get("failed", []) or []:
                if isinstance(item, dict):
                    parts.append(str(item.get("reason") or item.get("detail")
                                     or item.get("problems") or item.get("errors") or item)[:200])
                else:
                    parts.append(str(item)[:200])
            failure_detail = "; ".join(parts)[:500]
        # Verification summary first: it only reads capability states +
        # the loop report, so observers polling a terminal task status
        # always find the autonomy_report already written (no race).
        verification = self._verification_summary(tasks, task_id, report)
        self._emit_event("VERIFICATION_COMPLETED", correlation_id=correlation_id,
                         task_id=task_id,
                         passed_steps=int(verification.get("passed_steps", 0) or 0))
        try:
            if status == "completed":
                tasks.complete(task_id, result=summary)
                if goal_id:
                    self.goals.complete(goal_id)
            elif status == "partial":
                tasks.complete(task_id, result={**summary, "partial": True})
                if goal_id:
                    self.goals.complete(goal_id)
            elif status == "cancelled":
                try:
                    tasks.cancel(task_id)
                except Exception:
                    pass
                if goal_id:
                    try:
                        self.goals.cancel(goal_id)
                    except Exception:
                        pass
            else:
                tasks.fail(task_id, (failure_detail or str(report.get("failed", "")))[:300])
                _fail_goal(failure_detail or status)
        except Exception:
            pass
        if status not in ("completed", "partial"):
            try:
                self.consciousness.set_state("ERROR", f"execution {status}")
            except Exception:
                pass

        try:
            self.consciousness.transition("REFLECTING", f"reflecting:{task_id}")
        except Exception:
            try:
                self.consciousness.set_state("REFLECTING", f"reflecting:{task_id}")
            except Exception:
                pass
        try:
            self.reflect({"task_id": task_id, "status": status, "summary": summary})
            self._emit_event("REFLECTION_COMPLETED", correlation_id=correlation_id,
                             task_id=task_id, status=status)
        except Exception:
            pass
        verification = self._verification_summary(tasks, task_id, report)
        # Self-evaluation (Phase 12): structured, deterministic, stored.
        evaluation: dict = {}
        try:
            from cognition.self_evaluation.self_evaluator import SelfEvaluator
            evaluation = SelfEvaluator().evaluate_task({
                "status": status, "completed": report.get("completed", []),
                "failed": report.get("failed", []), "replans": report.get("replans", 0),
                "verification": verification,
                "planned_steps": len(plan),
                "step_descriptions": [str(s.get("description", "")) for s in plan]})
            self._trace(correlation_id, "reflection",
                        {"goal_satisfied": evaluation.get("goal_satisfied"),
                         "replans": evaluation.get("replans"),
                         "lesson": evaluation.get("lesson", "")[:160]})
            self._trace(correlation_id, "self_evaluation",
                        {"goal_satisfied": evaluation.get("goal_satisfied"),
                         "step_coverage": evaluation.get("step_coverage"),
                         "verification_coverage": evaluation.get("verification_coverage"),
                         "efficiency": evaluation.get("efficiency"),
                         "unnecessary_steps": evaluation.get("unnecessary_steps"),
                         "failed_assumptions": evaluation.get("failed_assumptions", [])[:3]})
        except Exception:
            evaluation = {}
        self._record_experience(stack, tasks, task_id, status == "completed",
                                evaluation=evaluation or None)
        try:
            self._record_world(task_id, status)
        except Exception:
            pass
        try:
            self._consolidate_memory()
        except Exception:
            pass
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        self._trace(correlation_id, "completion",
                    {"task_id": task_id, "status": status, "latency_ms": latency_ms})
        _log.info("[%s] REFLECTION→MEMORY→RESPONSE status=%s verified=%s latency_ms=%.2f",
                  correlation_id, status, verification.get("passed_steps"), latency_ms)
        _terminal_event = "GOAL_COMPLETED" if status in ("completed", "partial") else "GOAL_FAILED"
        self._emit_event(_terminal_event, correlation_id=correlation_id, task_id=task_id,
                         status=status, latency_ms=latency_ms)
        if status in ("completed", "partial"):
            try:
                self.consciousness.transition("COMPLETED", f"done:{task_id}")
                self.consciousness.set_state("ACTIVE", f"run_cycle {status}")
            except Exception:
                pass
        else:
            try:
                self.consciousness.set_state("ACTIVE", f"run_cycle {status}")
            except Exception:
                pass
        try:
            _reasoning_public = {
                "mode": str(_reasoning_decision.get("mode", "")),
                "model": str(_reasoning_decision.get("model", ""))[:120],
                "provider": str(_reasoning_decision.get("provider", "")),
                "reason": str(_reasoning_decision.get("reason", ""))[:200],
                "budget": dict(_reasoning_decision.get("budget", {}) or {}),
                "risk": str(_reasoning_decision.get("risk", "")),
                "latency_ms": float((self.last_reasoning or {}).get("latency_ms", 0.0) or 0.0),
                "passes": int((self.last_reasoning or {}).get("passes", 0) or 0)}
        except Exception:
            _reasoning_public = {"mode": "UNKNOWN"}
        result: dict = {
            "task_id": task_id, "status": status, "result": summary,
            "verification": verification,
            "goal_id": goal_id,
            "plan_mode": plan_mode,
            # UAI Phase N2/Step 34: skill provenance when the planner
            # adopted a validated skill ({} when none). Operational
            # metadata only — the skill already passed validation,
            # matching, policy, and verification like any plan.
            "skill": dict(plan_info.get("skill") or {}),
            "evaluation": evaluation,
            "retries": self._retry_count(tasks, task_id),
            "replans": int(report.get("replans", 0) or 0),
            "execution_summary": f"{len(report.get('completed', []))} completed, "
                                 f"{len(report.get('failed', []))} failed, "
                                 f"{report.get('replans', 0)} replans",
            "correlation_id": correlation_id, "latency_ms": latency_ms}
        if status in ("completed", "partial"):
            result["reasoning"] = _reasoning_public
        if status not in ("completed", "partial"):
            result["error"] = (
                f"subsystem='autonomous-loop' operation='execute' "
                f"exception='{failure_detail or status}' recovery='replan-exhausted' "
                f"result='failed'")
        return result

    @staticmethod
    def _plan_contract_problems(plan) -> list:
        """Every executable step must carry step_id, goal, capabilities, verification."""
        problems = []
        if not plan:
            return ["empty plan: no steps"]
        for i, step in enumerate(plan):
            sid = str(step.get("step_id", "") or "").strip()
            if not sid:
                problems.append(f"step-{i + 1}: missing step_id")
            goal = str(step.get("goal", step.get("objective", step.get("description", ""))) or "").strip()
            if not goal:
                problems.append(f"{sid or f'step-{i + 1}'}: missing goal/objective")
            if not step.get("required_capabilities"):
                problems.append(f"{sid or f'step-{i + 1}'}: MISSING_CAPABILITIES")
            if not step.get("verification_criteria"):
                problems.append(f"{sid or f'step-{i + 1}'}: MISSING_VERIFICATION")
        return problems

    def _autonomy_failure(self, goal, task_id, correlation_id, started,
                          subsystem="brain", operation="run_cycle", exception=None):
        """Structured failure with consciousness transition (ERROR → IDLE)."""
        import logging as _logging
        _logging.getLogger("HERCULE.RequestLifecycle").error(
            "[%s] FAILED subsystem='%s' operation='%s' exception='%s'",
            correlation_id, subsystem, operation, str(exception)[:200])
        try:
            self.consciousness.set_state("ERROR", f"{subsystem}:{operation}")
            try:
                self._autonomy_stack()["tasks"].fail(task_id, str(exception)[:300])
            except Exception:
                pass
            self.consciousness.set_state("IDLE", "failure recorded")
        except Exception:
            pass
        return self._failure_result(
            goal, "failed",
            f"subsystem='{subsystem}' operation='{operation}' "
            f"exception='{exception}' recovery='bounded-replan-or-report' result='failed'",
            correlation_id, started, task_id=task_id)

    ##################################################
    # Autonomous composition (lazy, orchestrator-first)
    ##################################################

    def _autonomy_stack(self):
        """Compose the verified stack from orchestrator services.

        Uses the orchestrator's TaskManager/AbilityManager/Memory when
        present (no second managers); constructs only what is missing.
        Ability defaults register only into an empty registry.
        """
        from abilities.tool_matcher import ToolMatcher
        from cognition.capabilities.registry import CapabilityRegistry
        from cognition.experience.experience_manager import ExperienceManager
        from orchestrator.autonomous import AutonomousLoop
        from security.permissions.policy_manager import PolicyManager
        from system.observability.trace import Tracer

        orchestrator = self.orchestrator
        tasks = getattr(orchestrator, "task_manager", None)
        if tasks is None:
            from cognition.task_manager.task_manager import TaskManager
            from orchestrator.orchestrator import _default_task_store
            tasks = TaskManager(storage_path=_default_task_store())
        abilities = getattr(orchestrator, "abilities", None)
        if abilities is None:
            from abilities.ability_manager import AbilityManager
            abilities = AbilityManager()
        if hasattr(abilities, "ensure_defaults"):
            abilities.ensure_defaults()
        elif hasattr(abilities, "count") and abilities.count() == 0 and hasattr(abilities, "register_defaults"):
            abilities.register_defaults()
        policy = getattr(abilities, "policy", None) or PolicyManager()
        registry = CapabilityRegistry()
        registry.register_default_tools(abilities if hasattr(abilities, "get") else None)
        agents = getattr(orchestrator, "agent_manager", None)
        for extra in getattr(self, "_extra_providers", []) or []:
            try:
                registry.register_provider(extra["capability"], extra["kind"], extra["name"],
                                           environments=extra.get("environments"),
                                           ability_manager=abilities, agent_manager=agents)
            except ValueError:
                pass  # already mapped
        if not hasattr(self, "_tool_tracker"):
            from abilities.tool_health import ToolHealthMonitor, ToolPerformanceTracker
            self._tool_tracker = ToolPerformanceTracker()
            self._tool_health = ToolHealthMonitor(tracker=self._tool_tracker)
        matcher = ToolMatcher(abilities, policy, agents, registry, self._tool_health)
        tracer = getattr(self, "_tracer", None)
        if tracer is None:
            tracer = Tracer()
            self._tracer = tracer
        experience = getattr(self, "_experience", None)
        if experience is None:
            experience = ExperienceManager()
            try:
                experience.load(self._experience_path())
            except Exception:
                pass
            self._experience = experience
        loop = AutonomousLoop(self.authoritative_planner, matcher, tasks, tracer)
        memory = getattr(orchestrator, "memory", None)
        return {"tasks": tasks, "abilities": abilities, "policy": policy, "registry": registry,
                "agents": agents, "matcher": matcher, "tracer": tracer, "experience": experience,
                "loop": loop, "memory": memory}

    def _trace(self, correlation_id, stage, data):
        tracer = getattr(self, "_tracer", None)
        if tracer is None or not correlation_id:
            return
        try:
            tracer.record(correlation_id, stage, data)
        except Exception:
            pass

    @staticmethod
    def _advance_quietly(tasks, task_id, action):
        try:
            if action == "queue":
                tasks.queue_task(task_id)
            elif action == "start":
                current = str(tasks.get(task_id).get("status", "")).upper()
                if current in ("CREATED", "QUEUED", "WAITING"):
                    tasks.start(task_id)
        except Exception:
            pass

    @staticmethod
    def _resume_quietly(tasks, task_id):
        try:
            tasks.resume(task_id)
        except Exception:
            pass

    def _resume_task(self, stack, tasks, task_id, plan, correlation_id):
        """Resume planning for tasks with prior progress.

        Returns a blocked-result dict when resume is unsafe (task left
        paused), else None after resetting replayable states and
        running compensations.
        """
        from orchestrator.resume import ResumePlanner

        matcher = stack.get("matcher")
        resume = ResumePlanner(tasks, matcher,
                               environment=getattr(matcher, "environment", "default") if matcher else "default")
        report = resume.plan(task_id, plan)
        self._trace(correlation_id, "resume_attempt", report.as_dict())
        if report.blocked:
            try:
                tasks.pause(task_id)
            except Exception:
                pass
            return {"task_id": task_id, "status": "blocked",
                    "result": {"decisions": report.as_dict()["decisions"]},
                    "verification": {}, "retries": self._retry_count(tasks, task_id), "replans": 0,
                    "execution_summary": "resume blocked: unsafe replay refused",
                    "correlation_id": correlation_id,
                    "latency_ms": 0.0}
        for decision in report.decisions:
            if decision.action != "COMPENSATE":
                continue
            step = next((s for s in plan if str(s.get("step_id", "")) == decision.step_id), None)
            outcome = resume.execute_compensation(step or {}, correlation_id)
            self._trace(correlation_id, "compensation",
                        {"step_id": decision.step_id, **outcome})
            if outcome.get("status") != "compensated":
                try:
                    tasks.pause(task_id)
                except Exception:
                    pass
                return {"task_id": task_id, "status": "blocked",
                        "result": {"decisions": report.as_dict()["decisions"],
                                   "compensation": outcome},
                        "verification": {}, "retries": self._retry_count(tasks, task_id), "replans": 0,
                        "execution_summary": "resume blocked: compensation failed",
                        "correlation_id": correlation_id, "latency_ms": 0.0}
        try:
            states = tasks.get(task_id).get("metadata", {}).get("capability_states", {})
            for sid in report.reset_steps:
                if sid in states:
                    states[sid]["status"] = "pending"
        except Exception:
            pass
        return None

    @staticmethod
    def _task_in_flight(tasks, task_id) -> bool:
        try:
            states = (tasks.get(task_id).get("metadata", {}) or {}).get("capability_states", {})
            if not isinstance(states, dict):
                return False
            return any(str((s or {}).get("status", "")).lower() in ("running", "executing")
                       for s in states.values())
        except Exception:
            return False

    @staticmethod
    def _task_has_progress(tasks, task_id) -> bool:
        try:
            task = tasks.get(task_id)
            states = (task.get("metadata", {}) or {}).get("capability_states", {})
            return bool(states) or bool(task.get("outputs")) or int(task.get("retry_count", 0) or 0) > 0
        except Exception:
            return False

    @staticmethod
    def _retry_count(tasks, task_id):
        try:
            return int(tasks.get(task_id).get("retry_count", 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _verification_summary(tasks, task_id, report):
        try:
            task = tasks.get(task_id)
            states = (task.get("metadata", {}) or {}).get("capability_states", {})
            passed = sum(1 for s in states.values()
                         if ((s or {}).get("verification") or {}).get("passed"))
            failed_steps = [f.get("step_id", "") for f in report.get("failed", []) if isinstance(f, dict)]
            task["metadata"]["autonomy_report"] = {
                "status": report.get("status"), "completed": report.get("completed", []),
                "failed": report.get("failed", []), "replans": report.get("replans", 0),
                "verified_steps": passed,
            }
            return {"passed_steps": passed, "failed_steps": failed_steps,
                    "state": task.get("verification_state", "")}
        except Exception:
            return {"passed_steps": 0, "failed_steps": [], "state": ""}

    def _record_experience(self, stack, tasks, task_id, succeeded, evaluation=None):
        """Distill task outcome → experience → durable memory (summaries only).

        ``evaluation`` is the structured self-evaluation (Phase 12); its
        lesson is stored with the experience when present.
        """
        import logging as _logging
        _log = _logging.getLogger("HERCULE.RequestLifecycle")
        try:
            task = tasks.get(task_id)
            # NOTE: record_rich() is the single recording path (it captures
            # everything record_from_task() did, plus capabilities/abilities/
            # lesson). Calling both would double-count one task as two
            # experiences, so the legacy call is intentionally omitted here.
            states = (task.get("metadata", {}) or {}).get("capability_states", {}) or {}
            capabilities: list = []
            abilities: list = []
            verified_abilities: list = []
            failures: list = []
            for state in states.values():
                for cap in (state or {}).get("required_capabilities", []) or []:
                    if cap not in capabilities:
                        capabilities.append(str(cap))
                tool = ((state or {}).get("selected_tool") or {}).get("name", "")
                verification = (state or {}).get("verification") or {}
                if tool and tool not in abilities:
                    abilities.append(str(tool))
                # Success lessons name only verified tools: fallback
                # candidates that never verified must not be credited.
                if tool and verification.get("passed") and tool not in verified_abilities:
                    verified_abilities.append(str(tool))
                if not verification.get("passed"):
                    failure = str((state or {}).get("failure", ""))[:200]
                    if failure and failure not in failures:
                        failures.append(failure)
            autonomy = (task.get("metadata", {}) or {}).get("autonomy_report", {}) or {}
            failed = autonomy.get("failed", []) or []
            for item in failed:
                if isinstance(item, dict):
                    detail = str(item.get("reason") or item.get("detail") or "")[:200]
                    if detail and detail not in failures:
                        failures.append(detail)
            verification_summary = {
                "passed_steps": sum(1 for s in states.values()
                                    if (s or {}).get("verification", {}).get("passed")),
                "state": task.get("verification_state", ""),
            }
            goal = str((task.get("metadata", {}) or {}).get("goal", "") or task_id)
            status = str(task.get("status", "FAILED"))
            record = stack["experience"].record_rich(
                goal, capabilities=capabilities,
                abilities=verified_abilities or abilities,
                verification=verification_summary,
                failure_reason="; ".join(failures)[:300],
                replans=int(autonomy.get("replans", 0) or 0),
                status=status, task_id=task_id,
                correlation_id=str((task.get("metadata", {}) or {}).get("correlation_id", "")))
            if isinstance(evaluation, dict) and evaluation.get("lesson"):
                # Annotate the stored record with the self-evaluation note.
                try:
                    record.lesson = f"{record.lesson[:220]} | self-eval: {evaluation['lesson'][:70]}"
                except Exception:
                    pass
            try:
                # The store path was bound when the manager loaded, so
                # save() reuses it instead of re-resolving ambient
                # configuration (UAI Phase M.1 incident class).
                stack["experience"].save()
            except Exception:
                pass
            correlation_id = str((task.get("metadata", {}) or {}).get("correlation_id", ""))
            self._trace(correlation_id or task_id, "experience",
                        {"outcome": record.outcome, "lesson": record.lesson[:160]})
            _log.info("EXPERIENCE outcome=%s lesson=[%.120s]", record.outcome, record.lesson)
            memory = stack.get("memory")
            if memory is not None and hasattr(memory, "remember_event"):
                memory.remember_event({"task_id": task_id, "status": task.get("status"),
                                       "goal": goal[:200],
                                       "correlation_id": (task.get("metadata", {}) or {}).get("correlation_id", "")})
                self._trace(correlation_id or task_id, "memory_write",
                            {"task_id": task_id, "outcome": record.outcome})
                _log.info("MEMORY_WRITE task=%s outcome=%s", task_id, record.outcome)
        except Exception:
            pass

    @staticmethod
    def _experience_path() -> str:
        from pathlib import Path as _Path
        from system.config.runtime_config import load_runtime_config
        from system.paths import resolve_data_path
        config = load_runtime_config()
        if str(config.experience_store or "").strip():
            return str(config.experience_store).strip()
        base = config.memory_dir
        directory = _Path(base) if base else _Path(resolve_data_path("data/memory"))
        return str(directory / "experiences.json")

    ##################################################
    # Memory coordination (Brain coordinates; MemoryManager stores)
    ##################################################

    def remember_fact(self, text: str, correlation_id: str = ""):
        """Store an explicitly user-directed fact. Returns a confirmation."""
        import re as _re
        fact = _re.sub(r"(?i)^\s*(please\s+)?remember\s+(that\s+)?", "", str(text or "")).strip()
        if not fact:
            return {"status": "failed",
                    "error": "empty memory directive: nothing to remember"}
        lowered = fact.lower()
        topic = "general"
        name_match = _re.search(r"(?i)(?:called|named|is)\s+([A-Za-z0-9_][\w\-.]*)", fact)
        about_match = _re.search(r"(?i)\bmy\s+([a-z][a-z \-]{1,40}?)\s+(is|are|was)\b", fact)
        if about_match:
            topic = about_match.group(1).strip().lower()
        elif name_match and len(fact.split()) <= 8:
            topic = "general"
        memory = getattr(self.orchestrator, "memory", None)
        if memory is None or not hasattr(memory, "remember_fact"):
            return {"status": "failed", "error": "memory subsystem unavailable"}
        try:
            stored = memory.remember_fact(topic, fact, correlation_id=correlation_id)
            return {"status": "remembered", "topic": topic,
                    "response": f"Remembered ({topic}): {fact}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:200]}

    def recall_memory(self, query: str = ""):
        """Recall explicitly stored facts (honest when empty)."""
        memory = getattr(self.orchestrator, "memory", None)
        if memory is None:
            return {"status": "failed", "error": "memory subsystem unavailable"}
        try:
            hits = memory.search_memory(query or "", memory_type="semantic", limit=10)
            if not hits and not (query or "").strip():
                facts = memory.facts()
                return {"status": "remembered", "facts": facts,
                        "response": self._format_facts(facts)}
            if not hits:
                return {"status": "empty",
                        "response": "I don't have anything stored about that."}
            facts = {r["record"]["metadata"].get("topic", "general"): r["record"]["content"]
                     for r in hits}
            return {"status": "remembered", "facts": facts,
                    "response": self._format_facts(facts)}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:200]}

    @staticmethod
    def _format_facts(facts: dict) -> str:
        if not facts:
            return "I don't have anything stored yet."
        return "Here's what I remember: " + "; ".join(
            f"{topic}: {content}" for topic, content in facts.items())[:1000]

    def observe_visual(self, source: str = "screenshot", path: str = "",
                       prompt: str = "") -> dict:
        """Explicit read-only visual observation (v1.1, additive).

        Runs perception -> structured observation, then attaches a
        concise observation summary for reasoning. Never exposes
        chain-of-thought; never executes actions. Raises honestly
        (VisionUnavailable/ValueError) when uncapturable or model-less.
        """
        from perception.vision.manager import VisionManager

        perception = getattr(getattr(self, "orchestrator", None), "perception", None)
        if perception is not None and hasattr(perception, "analyze_visual"):
            observation = perception.analyze_visual(source, path, prompt or "")
        else:
            manager = VisionManager()
            if str(source or "").lower() == "screenshot":
                observation = manager.analyze_screenshot(prompt or "")
            else:
                observation = manager.analyze_file(path, prompt or "")
        try:
            self._trace("", "visual_observation",
                        {"source": observation.get("source", source),
                         "confidence": observation.get("confidence", 0.0)})
        except Exception:
            pass
        summary = str(observation.get("description", ""))[:500]
        texts = observation.get("detected_text", []) or []
        if texts:
            summary += " Text: " + "; ".join(texts[:5])[:300]
        try:
            self._ingest_vision_world(observation)
        except Exception:
            pass
        return {"status": "observed", "observation": observation,
                "response": f"I see: {summary}"}

    def _ingest_vision_world(self, observation: dict) -> None:
        """Fold structured vision output into the world model.

        Only validated fields (regions with labels/confidence, model
        name, source) become OBSERVED object entities + a screen-state
        environment entity. Raw description prose never becomes state.
        """
        world = getattr(self, "world", None)
        if world is None or not isinstance(observation, dict):
            return
        source = "vision" if observation.get("source") == "screenshot" else "vision"
        regions = observation.get("regions", []) or []
        for region in regions[:20]:
            if not isinstance(region, dict):
                continue
            label = str(region.get("label", "") or "").strip()
            if not label:
                continue
            try:
                conf = float(region.get("confidence", 0.5) or 0.5)
            except (TypeError, ValueError):
                conf = 0.5
            world.observe(source, "object", label,
                          {"screen_region": {k: region.get(k) for k in
                                             ("x", "y", "width", "height")},
                           "model": str(observation.get("model", ""))},
                          f"seen on {observation.get('source', 'screen')}",
                          confidence=min(1.0, max(0.0, conf)))
        world.observe(source, "environment", "screen",
                      {"state": "observed",
                       "model": str(observation.get("model", ""))},
                      str(observation.get("description", ""))[:200],
                      confidence=float(observation.get("confidence", 0.5) or 0.5))

    def world_context(self, query: str) -> str:
        """Bounded world-state slice for prompts (empty when none)."""
        try:
            world = getattr(self, "world", None)
            if world is None:
                return ""
            return world.context_for(query or "")
        except Exception:
            return ""

    def decide_reasoning(self, text: str, is_question: bool = False,
                         context: Optional[dict] = None) -> dict:
        """Adaptive reasoning decision (v2 Phase 4, additive).

        Returns {"mode","model","provider","reason","budget",
        "risk",...} without executing anything. The controller reuses
        ModelManager/Router metadata (installed models only) plus
        world-resolver shortcuts and experience promotion. Never
        exposes chain-of-thought.
        """
        from cognition.reasoning.controller import AdaptiveReasoningController

        try:
            controller = AdaptiveReasoningController(
                getattr(self.orchestrator, "models", None))
            payload = dict(context or {})
            try:
                if "world_resolver" not in payload:
                    from world.resolver import WorldResolver

                    world = getattr(self, "world", None)
                    if world is not None:
                        tasks = getattr(getattr(self.orchestrator, "memory", None),
                                        "tasks", None)
                        payload["world_resolver"] = WorldResolver(world)
            except Exception:
                pass
            try:
                if "experience_stats" not in payload:
                    relevant = self.relevant_experiences(text or "", limit=5) or []
                    payload["experience_stats"] = self._experience_success_stats(relevant)
            except Exception:
                pass
            decision = controller.decide(text or "", context=payload,
                                         is_question=is_question)
            self.last_reasoning = dict(decision)
            return decision
        except Exception as exc:
            fallback = {"mode": "STANDARD", "model": "", "provider": "",
                        "reason": f"controller fallback: {exc}",
                        "budget": {"max_tokens": 256, "timeout_s": 30,
                                   "max_passes": 1, "max_context_chars": 1500,
                                   "max_tool_calls": 8},
                        "risk": "LOW", "complexity": 0, "signals": {},
                        "capabilities": [], "shortcut": ""}
            self.last_reasoning = dict(fallback)
            return fallback

    def reason_with_decision(self, problem: str, decision: Optional[dict] = None) -> dict:
        """Budgeted reasoning under an adaptive decision (summaries only)."""
        from cognition.reasoning.controller import AdaptiveReasoningController

        decision = dict(decision or self.last_reasoning or {})
        if decision.get("mode", "STANDARD") == "DETERMINISTIC":
            try:
                return {"status": "skipped", "summary": str(self.reasoning.reason(problem))[:500]}
            except Exception as exc:
                return {"status": "failed", "error": str(exc)[:300]}
        try:
            controller = AdaptiveReasoningController(
                getattr(self.orchestrator, "models", None))
            outcome = controller.reason_budgeted(str(problem), decision)
            try:
                self.last_reasoning = {**decision,
                                       "latency_ms": outcome.get("latency_ms", 0.0),
                                       "passes": outcome.get("passes", 0)}
            except Exception:
                pass
            return outcome
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def build_brain_context(self, query: str) -> str:
        """Layered bounded context (v2): world + memories + experience
        + task state. Each layer is capped; the whole is capped. Empty
        stores contribute nothing (never fabricated filler)."""
        parts: List[str] = []
        try:
            world_slice = self.world_context(query or "")
            if world_slice:
                parts.append(world_slice[:400])
        except Exception:
            pass
        try:
            memory = getattr(self.orchestrator, "memory", None)
            if memory is not None and hasattr(memory, "retrieve_relevant"):
                hits = memory.retrieve_relevant(query or "", limit=4) or []
                lines = [str(h.get("record", {}).get("content", ""))[:140]
                         for h in hits if h.get("record", {}).get("content")]
                if lines:
                    parts.append("Relevant memories:\n" + "\n".join(lines)[:500])
        except Exception:
            pass
        try:
            relevant = self.relevant_experiences(query or "", limit=2) or []
            lessons = [str(e.get("lesson", ""))[:140] for e in relevant
                       if e.get("lesson")]
            if lessons:
                parts.append("Past lessons:\n" + "\n".join(lessons)[:300])
        except Exception:
            pass
        try:
            goals = getattr(self, "goals", None)
            if goals is not None and hasattr(goals, "active_goals"):
                active = goals.active_goals() or []
                if active:
                    first = active[0] or {}
                    parts.append(f"Active goal: {str(first.get('goal', ''))[:140]}")
        except Exception:
            pass
        return "\n".join(parts)[:1500]

    def _consolidate_memory(self) -> dict:
        """End-of-cycle memory consolidation (bounded, best-effort)."""
        try:
            memory = getattr(self.orchestrator, "memory", None)
            if memory is None or not hasattr(memory, "consolidate"):
                return {}
            experiences: list = []
            try:
                stack = self._autonomy_stack()
                exp_manager = stack.get("experience")
                if exp_manager is not None and hasattr(exp_manager, "query"):
                    experiences = exp_manager.query(limit=20) or []
            except Exception:
                experiences = []
            return memory.consolidate(experiences=experiences) or {}
        except Exception:
            return {}

    def _record_world(self, task_id: str, status: str) -> None:
        """Task/file outcomes -> world state (references TaskManager).

        Task entities mirror live TaskManager status (never a separate
        authority). Verified file writes/reads become KNOWN file
        entities only after an existence check.
        """
        try:
            world = getattr(self, "world", None)
            tasks = getattr(getattr(self, "orchestrator", None), "task_manager", None)
            if world is None or tasks is None or not task_id:
                return
            try:
                task = tasks.get(task_id)
            except Exception:
                task = None
            if not isinstance(task, dict):
                return
            goal = str((task.get("metadata", {}) or {}).get("goal", "")
                       or task.get("goal", "") or task_id)[:200]
            live_status = str(task.get("status", status or "")) or status
            world.observe("task", "task", goal or task_id,
                          {"status": live_status, "task_id": task_id},
                          f"task {task_id} {live_status}",
                          confidence=0.9, verified=True)
            if status in ("completed", "partial"):
                self._record_world_files(world, goal, task_id)
        except Exception:
            pass

    def _record_world_files(self, world, goal: str, task_id: str) -> None:
        """Verified file mentions -> KNOWN file entities (existence-checked).

        Only files that actually exist in the workspace sandbox become
        KNOWN; everything else stays unrecorded (no guessing).
        """
        try:
            from cognition.planner.references import extract_file_mentions
            from abilities.files.file_ability import _workspace

            workspace = _workspace()
            for name in extract_file_mentions(goal or ""):
                try:
                    candidate = (workspace / name).resolve()
                    try:
                        candidate.relative_to(workspace.resolve())
                    except ValueError:
                        continue
                    if candidate.is_file():
                        world.observe_file(str(candidate), True,
                                           source="task",
                                           evidence=f"verified by task {task_id}")
                except Exception:
                    continue
        except Exception:
            pass

    def run_computer_sequence(self, proposals: list) -> dict:
        """Bounded computer-use sequence (v1.2, additive).

        Proposals are structured mappings (never raw text). Runs the
        shared controller's OBSERVE -> APPROVE -> ACT -> VERIFY loop
        with enforced bounds. Single actions flow through the normal
        run_cycle/ability path instead; this helper is for explicit
        multi-step desktop procedures.
        """
        from computer.controller import shared_controller

        result = shared_controller().run_sequence(list(proposals or []))
        try:
            self._ingest_computer_world(result)
        except Exception:
            pass
        return result

    def _ingest_computer_world(self, result: dict) -> None:
        """Verified computer outcomes -> application entities only."""
        world = getattr(self, "world", None)
        if world is None or not isinstance(result, dict):
            return
        steps = result.get("steps")
        if not isinstance(steps, list):
            return
        for entry in steps:
            if not isinstance(entry, dict):
                continue
            action = entry.get("action", {})
            if not isinstance(action, dict):
                continue
            if action.get("action") == "open_app" and entry.get("verified"):
                world.observe_application(
                    str(action.get("app", "")), "running",
                    evidence="verified computer open_app", verified=True)

    def recall_session(self):
        """Summarize the previous persisted session (durable events only)."""
        memory = getattr(self.orchestrator, "memory", None)
        if memory is None:
            return {"status": "failed", "error": "memory subsystem unavailable"}
        try:
            events = memory.search_memory("task conversation", memory_type="episodic", limit=10)
            tasks = memory.search_memory("task", memory_type="episodic", limit=10)
            seen = set()
            lines = []
            for entry in (events + tasks):
                content = entry["record"]["content"]
                if content in seen:
                    continue
                seen.add(content)
                lines.append(content)
            if not lines:
                return {"status": "empty",
                        "response": "I don't have any previous session activity stored."}
            return {"status": "remembered",
                    "response": "Previous session: " + "; ".join(lines[:8])[:1000]}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:200]}

    def relevant_experiences(self, goal: str, limit: int = 3):
        """Concise past-experience summaries relevant to a goal (no CoT)."""
        try:
            stack = self._autonomy_stack()
            found = stack["experience"].find_relevant(goal, limit=limit)
            return [{"outcome": e.outcome, "capabilities": list(e.capabilities),
                     "abilities": list(e.abilities), "lesson": e.lesson,
                     "success": e.success} for e in found]
        except Exception:
            return []

    def _experience_success_stats(self, relevant):
        """Per-capability mean success from retrieved experiences."""
        totals: dict = {}
        counts: dict = {}
        for entry in relevant or []:
            try:
                success = float(entry.get("success", 0.0))
            except (TypeError, ValueError):
                continue
            for cap in entry.get("capabilities", []) or []:
                key = str(cap).upper()
                totals[key] = totals.get(key, 0.0) + success
                counts[key] = counts.get(key, 0) + 1
        return {key: totals[key] / counts[key] for key in totals}

    def _planner_memory_context(self, goal: str, relevant) -> str:
        """Bounded advisory context for planning (never the whole store)."""
        try:
            from cognition.planner.cognitive import build_memory_context
            memory = getattr(self.orchestrator, "memory", None)
            facts: dict = {}
            procedures: list = []
            if memory is not None:
                try:
                    if hasattr(memory, "search_memory"):
                        for hit in memory.search_memory(goal, limit=3) or []:
                            record = (hit or {}).get("record", {}) or {}
                            topic = str((record.get("metadata", {}) or {}).get(
                                "topic", record.get("memory_type", "fact")))
                            content = str(record.get("content", ""))[:120]
                            if content and topic not in facts:
                                facts[topic] = content
                except Exception:
                    pass
                try:
                    if hasattr(memory, "facts"):
                        for topic, info in list(memory.facts().items())[:3]:
                            facts.setdefault(str(topic), str(info)[:120])
                except Exception:
                    pass
            try:
                stack = self._autonomy_stack()
                experience = stack.get("experience")
                if experience is not None and hasattr(experience, "find_relevant"):
                    seen_types: set = set()
                    for record in experience.find_relevant(goal, limit=3) or []:
                        goal_type = str(getattr(record, "goal_type", "") or "")
                        if not goal_type or goal_type in seen_types:
                            continue
                        seen_types.add(goal_type)
                        try:
                            proposal = experience.propose_procedure(goal_type)
                        except Exception:
                            proposal = None
                        if proposal is not None and getattr(proposal, "validated", False):
                            procedures.append({"steps": list(getattr(proposal, "steps", []) or [])})
            except Exception:
                pass
            return build_memory_context(relevant, procedures, facts)
        except Exception:
            return ""

    def _planning_timeout_s(self) -> float:
        from system.config.runtime_config import load_runtime_config
        try:
            return max(10.0, float(load_runtime_config().planning_timeout_s))
        except (TypeError, ValueError):
            return 90.0

    def plan_with_policy(self, goal: str, step_texts, decomposed: bool,
                         reasoning_summary: str, planner_context: str,
                         correlation_id: str, semantic=None, proposer=None,
                         allow_skills: bool = False):
        """Hybrid planning: deterministic always, cognitive when warranted.

        Returns (plan, mode, info) where mode is "deterministic" or
        "cognitive" and info carries policy/decision/proposal metadata.
        The deterministic plan is always built first (cheap); the model
        proposes at most one candidate; DecisionEngine selects between
        validated candidates only. Any model failure falls back honestly.

        ``allow_skills`` (goal-derived requests only, never explicit
        caller steps) lets the planner adopt a validated skill's
        procedure; the adopted steps still pass validation, matching,
        policy, and verification. ``info["skill"]`` carries provenance.
        """
        import logging as _logging
        _log = _logging.getLogger("HERCULE.RequestLifecycle")
        from cognition.planner.cognitive import planning_policy

        planner = self.authoritative_planner
        det_plan = planner.create_capable_plan(
            goal, list(step_texts), semantic=semantic, proposer=proposer,
            chain=decomposed, allow_skills=allow_skills)
        policy = planning_policy(goal)
        info: dict = {"policy": policy, "mode": "deterministic", "decision": {}}
        try:
            skill_steps = [s for s in det_plan
                           if isinstance(s, dict) and s.get("skill_id")]
            if skill_steps:
                info["skill"] = {
                    "skill_id": skill_steps[0].get("skill_id", ""),
                    "version": skill_steps[0].get("skill_version", ""),
                    "procedure": [str(s.get("description", "")) for s in det_plan],
                }
        except Exception:
            pass
        if policy.get("mode") != "cognitive":
            _log.info("[%s] PLAN_POLICY mode=deterministic reason=[%s]",
                      correlation_id, policy.get("reason", "")[:120])
            return det_plan, "deterministic", info
        try:
            self.consciousness.transition("DECIDING", f"decide-plan:{goal[:60]}")
        except Exception:
            pass
        proposal, metrics, proposal_error = self._propose_cognitive_plan(
            goal, reasoning_summary, planner_context, correlation_id)
        info["proposal"] = {"ok": proposal is not None, "error": proposal_error,
                            "metrics": metrics}
        candidates = [{"mode": "deterministic", "plan": det_plan,
                       "validation": self._validate_plan_for_decision(det_plan)}]
        if proposal is not None:
            candidates.append({"mode": "cognitive", "plan": proposal,
                               "validation": self._validate_plan_for_decision(proposal)})
        else:
            _log.info("[%s] PLAN_PROPOSAL failed, deterministic fallback: %s",
                      correlation_id, proposal_error[:160])
        try:
            stack = self._autonomy_stack()
            abilities = stack.get("abilities")
            matcher = stack.get("matcher")
            registry = getattr(matcher, "registry", None)
        except Exception:
            abilities = None
            matcher = None
            registry = None
        try:
            stats = self._experience_success_stats(
                self.relevant_experiences(goal, limit=5))
        except Exception:
            stats = {}
        try:
            time_budget = self._autonomy_stack()["loop"].max_total_execution_time
        except Exception:
            time_budget = None
        # Phase 5 (Decision Intelligence): build CandidateStrategy records
        # from validated plan candidates and let the authoritative decision
        # layer rank them. The model proposed at most one candidate; it never
        # decides. World-model state informs fit but never authority.
        world_state: dict = {}
        try:
            world = getattr(self, "world", None)
            if world is not None and hasattr(world, "snapshot"):
                world_state = dict(world.snapshot())
        except Exception:
            world_state = {}
        available_capabilities: list = []
        try:
            if registry is not None:
                available_capabilities = [str(c) for c in registry.capabilities()]
        except Exception:
            available_capabilities = []
        available_abilities: list = []
        try:
            if abilities is not None and hasattr(abilities, "abilities"):
                available_abilities = [str(a) for a in abilities.abilities()]
        except Exception:
            available_abilities = []
        from cognition.decision.strategy import (
            CandidateStrategy,
            decide_strategies,
            normalize_risk,
        )

        def _cap_risk(cap: str) -> str:
            try:
                from cognition.capabilities.capability import (
                    CAPABILITY_RISK, Capability,
                )
                return CAPABILITY_RISK[Capability(str(cap).upper())].value
            except Exception:
                return "LOW"

        def _plan_to_candidate(mode: str, plan) -> CandidateStrategy:
            caps: list = []
            abil: list = []
            deps: list = []
            steps_view: list = []
            high = med = 0
            verified = 0
            for s in (plan or []):
                scaps = [str(c).upper() for c in (s.get("required_capabilities") or [])]
                caps.extend(scaps)
                ab = str(s.get("required_ability", "") or "")
                if ab:
                    abil.append(ab)
                deps.extend(str(d) for d in (s.get("dependencies") or []))
                if s.get("verification_criteria"):
                    verified += 1
                sr = str(s.get("risk", "LOW")).upper()
                if sr not in ("LOW", "MEDIUM", "HIGH"):
                    sr = max((_cap_risk(c) for c in scaps), key=lambda r: ("LOW", "MEDIUM", "HIGH").index(r) if r in ("LOW", "MEDIUM", "HIGH") else -1) if scaps else "LOW"
                if sr == "HIGH":
                    high += 1
                elif sr == "MEDIUM":
                    med += 1
                steps_view.append({"step_id": str(s.get("step_id", "")),
                                   "goal": str(s.get("goal", s.get("description", s.get("objective", "")))),
                                   "required_capabilities": scaps,
                                   "risk": sr})
            capset = list(dict.fromkeys(caps))
            overall = "HIGH" if high else ("MEDIUM" if med else "LOW")
            n = max(1, len(list(plan or [])))
            vdiff = ("STRONG" if verified == len(list(plan or [])) and list(plan or [])
                     else ("MINIMAL" if verified == 0 else "STANDARD"))
            return CandidateStrategy(
                strategy_id=f"{mode}-{n}",
                goal=goal,
                steps=steps_view,
                required_capabilities=capset,
                required_abilities=abil,
                dependencies=deps,
                estimated_cost=float(len(list(plan or []))),
                estimated_latency_s=float(n * 30.0),
                risk=normalize_risk(overall),
                verification_difficulty=vdiff,
                expected_success=max(0.0, min(1.0, (
                    sum(float(stats.get(c, 0.5)) for c in capset) / max(1, len(capset))))) if capset else 0.5,
                experience_support=min(1.0, max(
                    (float(stats.get(c, 0.0)) for c in capset), default=0.0)),
                source=mode,
            )

        cs_candidates: list = []
        rejected: list = []
        det_validation = candidates[0].get("validation") or {}
        if det_validation.get("valid") and det_plan:
            cs_candidates.append(_plan_to_candidate("deterministic", det_plan))
        elif not det_plan:
            # Policy gate downstream re-validates the deterministic plan
            # anyway; an empty deterministic plan still wins over "no
            # candidate" so permission problems surface honestly at the
            # same place they did before Phase 5.
            cs_candidates.append(_plan_to_candidate("deterministic", det_plan))
            rejected.append({"strategy_id": "deterministic",
                             "reason": "deterministic plan empty (validation problems recorded)"})
        else:
            cs_candidates.append(_plan_to_candidate("deterministic", det_plan))
            rejected.append({"strategy_id": "deterministic",
                             "reason": "; ".join(
                                 str(p.get("detail", p))[:80]
                                 for p in (det_validation.get("problems") or [])[:3])})
        if proposal is not None:
            prop_validation = candidates[1].get("validation") or {}
            if prop_validation.get("valid"):
                cs_candidates.append(_plan_to_candidate("cognitive", proposal))
            else:
                rejected.append({
                    "strategy_id": "cognitive",
                    "reason": "; ".join(
                        str(p.get("detail", p))[:80]
                        for p in (prop_validation.get("problems") or [])[:3]),
                })
        rec = decide_strategies(
            goal, cs_candidates,
            experience_stats=stats,
            available_abilities=available_abilities or None,
            available_capabilities=available_capabilities or None,
            environment=getattr(matcher, "environment", "default"),
            world_state=world_state or None,
            decision_time_ms=None,
        )
        selected = rec.selected
        info["decision"] = {
            "candidates": len(cs_candidates),
            "valid_candidates": [c.strategy_id for c in rec.valid_candidates],
            "rejected_candidates": rejected or rec.rejected_candidates,
            "scores": dict(rec.scores),
            "selected_strategy": selected.strategy_id if selected else None,
            "selection_reason": rec.selection_reason,
            "dominated": {k: {"dominated": v.dominated, "by": v.by}
                          for k, v in rec.dominated.items()},
            "decision_time_ms": round(rec.decision_time_ms, 3),
            "choice": str(selected.source) if selected else "deterministic",
        }
        _log.info("[%s] DECISION candidates=%d selected=%s scores=%s reason=[%s]",
                  correlation_id, len(cs_candidates),
                  info["decision"]["selected_strategy"],
                  {k: round(v, 2) for k, v in rec.scores.items()},
                  rec.selection_reason[:160])
        if not selected:
            # No validated candidate: honest failure, nothing executed.
            info["decision"]["choice"] = "none"
            return [], "none", info
        chosen_plan = det_plan if selected.source == "deterministic" else proposal
        return list(chosen_plan or det_plan), str(selected.source), info

    def _validate_plan_for_decision(self, plan) -> dict:
        """Lightweight validity verdict for plan selection (full gate later)."""
        try:
            from cognition.planner.validation import validate_plan
            stack = self._autonomy_stack()
            matcher = stack.get("matcher")
            return validate_plan(
                plan,
                capability_registry=getattr(matcher, "registry", None),
                policy_manager=getattr(matcher, "policy", None),
                environment=getattr(matcher, "environment", "default"),
                ability_manager=getattr(matcher, "abilities", None),
                agent_manager=getattr(matcher, "agents", None),
                goal="decision-candidate")
        except Exception as exc:
            return {"valid": False, "problems": [{"code": "VALIDATION_ERROR",
                                                  "detail": str(exc)[:160]}]}

    def _propose_cognitive_plan(self, goal: str, reasoning_summary: str,
                                planner_context: str, correlation_id: str):
        """One bounded model call → validated capable steps (or None)."""
        import logging as _logging
        _log = _logging.getLogger("HERCULE.RequestLifecycle")
        from cognition.planner.cognitive import propose_plan, plan_from_proposal

        stack = self._autonomy_stack()
        abilities = stack.get("abilities")
        # Narrow the proposal allowlists to capabilities relevant to this
        # goal plus their registered providers: smaller prompts decode
        # faster, and the model cannot wander outside the task's scope.
        # Full validation still applies downstream regardless.
        allowed_capabilities: list = []
        allowed_abilities: list = []
        try:
            from cognition.capabilities.inference import infer_capabilities
            allowed_capabilities = [c.value for c in infer_capabilities(goal)]
        except Exception:
            allowed_capabilities = []
        try:
            registry = getattr(stack.get("matcher"), "registry", None)
            if registry is not None:
                for cap in allowed_capabilities:
                    try:
                        for provider in registry.providers_for(cap, "default"):
                            name = getattr(provider, "name", "")
                            if name and name not in allowed_abilities:
                                allowed_abilities.append(str(name))
                    except Exception:
                        continue
        except Exception:
            pass
        if not allowed_capabilities:
            try:
                from cognition.capabilities.capability import Capability
                allowed_capabilities = [c.value for c in Capability]
            except Exception:
                allowed_capabilities = []
        if not allowed_abilities:
            try:
                allowed_abilities = list(abilities.abilities()) if hasattr(abilities, "abilities") else []
            except Exception:
                allowed_abilities = []
        models = getattr(self.orchestrator, "models", None)
        if models is None:
            return None, {}, "no model manager bound"
        self._trace(correlation_id, "plan_proposal",
                    {"status": "requested", "abilities": len(allowed_abilities)})
        ok, proposal, error, metrics = propose_plan(
            models, goal, reasoning_summary or goal[:200], planner_context,
            allowed_capabilities, allowed_abilities,
            timeout_s=self._planning_timeout_s())
        self._trace(correlation_id, "plan_proposal",
                    {"status": "received" if ok else "failed",
                     "model": metrics.get("model", ""), "error": error[:160]})
        _log.info("[%s] PLAN_PROPOSAL ok=%s model=%s", correlation_id, ok,
                  metrics.get("model", ""))
        if not ok:
            return None, metrics, error
        try:
            steps = plan_from_proposal(goal, proposal)
        except Exception as exc:
            return None, metrics, f"proposal conversion failed: {exc}"
        contract = self._plan_contract_problems(steps)
        if contract:
            return None, metrics, f"proposal failed contract: {contract}"
        return steps, metrics, ""

    def _cognitive_replan_fn(self, goal: str, planner_context: str,
                             correlation_id: str):
        """Build an adaptive replan proposer for the execution loop.

        Returns fn(failed_step, observation_summary) -> [descriptions].
        The model suggests alternative step wordings; deterministic
        inference + plan validation still gate everything.
        """
        from models.structured import extract_json

        def propose(failed_step, observation_summary):
            models = getattr(self.orchestrator, "models", None)
            if models is None:
                raise RuntimeError("no model manager bound")
            description = str((failed_step or {}).get("description", ""))
            prompt = (
                "You propose RECOVERY STEPS for a failed automation step. "
                "You do NOT execute anything. Rules: at most 2 steps, plain "
                "action language, no tool names as commands.\n"
                f"\nOriginal goal:\n{goal}"
                f"\n\nFailed step:\n{description}"
                f"\n\nVerified observation:\n{observation_summary}"
                f"\n\nAdvisory context:\n{planner_context}"
                '\n\nRespond with JSON only: {"steps": [{"goal": "<alternative action>"}, ...]}'
            )
            raw = models.generate(prompt, timeout_s=self._planning_timeout_s())
            if isinstance(raw, str) and raw.startswith("[HERCULE Error]"):
                raise RuntimeError(f"model unavailable: {raw[:160]}")
            ok, data, error = extract_json(raw)
            if not ok or not isinstance(data, dict):
                raise RuntimeError(f"replan proposal not JSON: {error[:160]}")
            items = data.get("steps", [])
            if not isinstance(items, list) or not items:
                raise RuntimeError("replan proposal has no steps")
            descriptions = [str(s.get("goal", "")).strip() for s in items[:2]
                            if isinstance(s, dict) and str(s.get("goal", "")).strip()]
            if not descriptions:
                raise RuntimeError("replan proposal steps are empty")
            self._trace(correlation_id, "plan_proposal",
                        {"status": "replan-received", "steps": len(descriptions)})
            return descriptions

        return propose

    @staticmethod
    def _reasoning_public(decision=None, last=None) -> dict:
        """Public reasoning-decision readout (observability, no CoT)."""
        try:
            source = dict(decision or last or {})
            if not source:
                return {"mode": "UNKNOWN"}
            return {
                "mode": str(source.get("mode", "UNKNOWN")),
                "model": str(source.get("model", ""))[:120],
                "provider": str(source.get("provider", "")),
                "reason": str(source.get("reason", ""))[:200],
                "budget": dict(source.get("budget", {}) or {}),
                "risk": str(source.get("risk", "")),
                "latency_ms": float(source.get("latency_ms", 0.0) or 0.0),
                "passes": int(source.get("passes", 0) or 0)}
        except Exception:
            return {"mode": "UNKNOWN"}

    @staticmethod
    def _failure_result(goal, status, error, correlation_id, started, task_id="",
                        reasoning=None):
        import time
        return {"task_id": task_id, "status": status, "result": {}, "verification": {},
                "retries": 0, "execution_summary": "", "error": str(error)[:300],
                "reasoning": dict(reasoning or {"mode": "UNKNOWN"}),
                "correlation_id": correlation_id,
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 3)}

    ##################################################
    # Task lifecycle delegation (no orphans)
    ##################################################

    def register_capability(self, capability, kind, name, environments=None):
        """Map an extra tool/agent as a capability provider for runs."""
        providers = getattr(self, "_extra_providers", None)
        if providers is None:
            providers = []
            self._extra_providers = providers
        providers.append({"capability": capability, "kind": kind, "name": name,
                          "environments": environments})
        return True

    def cancel_task(self, task_id: str):
        return self._autonomy_stack()["tasks"].cancel(task_id)

    def pause_task(self, task_id: str):
        return self._autonomy_stack()["tasks"].pause(task_id)

    def resume_task(self, task_id: str):
        return self._autonomy_stack()["tasks"].resume(task_id)

    def task_status(self, task_id: str):
        tasks = self._autonomy_stack()["tasks"]
        return {"task_id": task_id, "status": tasks.status(task_id)}

    ##################################################
    # Semantic Capability Configuration
    ##################################################

    def configure_semantic(
        self,
        config=None,
        proposer=None,
        enabled=None,
        mode=None,
        shadow=None,
        required=None,
        min_confidence=None,
        low_confidence=None,
        max_retries=None,
        timeout_s=None,
        cache_enabled=None,
        model=None,
        **resolver_kwargs,
    ):
        """Configure default semantic capability resolution for run_cycle.

        Persists a SemanticCapabilityProposer + resolver configuration on
        the canonical Planner so ``run_cycle(use_semantic=None)`` (the
        default-arg path) picks up the configured behavior instead of
        the legacy deterministic-only path.

        When ``proposer`` is not given but a SemanticConfig is provided,
        no automatic proposer is built here — the caller retains control
        over model/router selection. Use RuntimeInitializer for a
        production-grade default proposer wired to ModelManager/Router.

        ``resolver_kwargs`` forward to ``resolve_capabilities`` on every
        plan step: registry, policy, ability_manager, agent_manager,
        environment, proposal_cache, tracer, etc.
        """
        from system.config.semantic_config import (
            SemanticConfig, apply_to_proposer, load_semantic_config, mode_for_config,
        )
        if config is None:
            config = SemanticConfig()
        if isinstance(config, dict):
            config = load_semantic_config(config)
        if enabled is not None:
            config.enabled = bool(enabled)
        if mode is not None:
            from cognition.capabilities.hybrid import HybridMode
            config.mode = HybridMode(str(mode).lower()) if isinstance(mode, str) else mode
        if shadow is not None:
            config.shadow = bool(shadow)
        if required is not None:
            config.required = bool(required)
        if min_confidence is not None:
            config.min_confidence = float(min_confidence)
        if low_confidence is not None:
            config.low_confidence = str(low_confidence)
        if max_retries is not None:
            config.max_retries = int(max_retries)
        if timeout_s is not None:
            config.timeout_s = float(timeout_s)
        if cache_enabled is not None:
            config.cache_enabled = bool(cache_enabled)
        if model is not None:
            config.model = str(model)
        if proposer is not None:
            try:
                apply_to_proposer(proposer, config)
            except Exception:
                pass
        self._semantic_config = config
        effective_mode = mode_for_config(config)
        if "registry" not in resolver_kwargs or "policy" not in resolver_kwargs:
            try:
                abilities = getattr(self.orchestrator, "abilities", None)
                policy = getattr(abilities, "policy", None)
                if "policy" not in resolver_kwargs and policy is not None:
                    resolver_kwargs["policy"] = policy
                if "ability_manager" not in resolver_kwargs and abilities is not None:
                    resolver_kwargs["ability_manager"] = abilities
                if "registry" not in resolver_kwargs:
                    from cognition.capabilities.registry import CapabilityRegistry
                    registry = CapabilityRegistry()
                    try:
                        registry.register_default_tools(
                            abilities if hasattr(abilities, "get") else None)
                    except Exception:
                        pass
                    resolver_kwargs["registry"] = registry
            except Exception:
                pass
        self.authoritative_planner.configure_semantic(
            proposer=proposer,
            mode=effective_mode,
            enabled=config.enabled,
            resolver_kwargs=resolver_kwargs,
        )
        return self

    ##################################################
    # Pipeline stages (LEGACY/DEPRECATED direct-execution path)
    #
    # Disposition: DEPRECATED. These stages bypass TaskManager,
    # PolicyManager and Verification (model output per step, no
    # capability checks). They remain functional for direct
    # orchestrator.pipeline users; run_cycle no longer uses them.
    # Migrate to run_cycle -> AutonomousLoop.
    ##################################################

    def _reason_stage(self, prompt: str):
        """DEPRECATED: isolated for backwards compat only; never used by run_cycle."""
        import logging as _logging
        _logging.getLogger("HERCULE.Brain").warning(
            "DEPRECATED _reason_stage called: bypasses task/policy/verification; migrate to run_cycle")
        try:
            reasoning = self.orchestrator.models.generate(f"Reason about: {prompt}")
        except Exception:
            reasoning = {"reasoning": prompt}

        return {"prompt": prompt, "reasoning": reasoning}

    def _plan_stage(self, data: dict):
        """DEPRECATED: isolated for backwards compat only; never used by run_cycle."""
        import logging as _logging
        _logging.getLogger("HERCULE.Brain").warning(
            "DEPRECATED _plan_stage called: bare-dict plan without capabilities; migrate to run_cycle")
        # Create a simple plan from reasoning output
        reasoning_text = data.get("reasoning") if isinstance(data, dict) else str(data)
        plan = self.planner.create(reasoning_text)
        return {**data, "plan": plan}

    def _execute_stage(self, data: dict):
        """DEPRECATED: isolated for backwards compat only; never used by run_cycle."""
        import logging as _logging
        _logging.getLogger("HERCULE.Brain").warning(
            "DEPRECATED _execute_stage called: bypasses policy/verification; migrate to run_cycle")
        # Execute each plan step via the orchestrator executor using the model for step execution
        results = []
        plan = data.get("plan") or []
        for step in plan:
            def task(step_goal=step.get("goal")):
                # Use model to 'execute' the step and produce a result
                return self.orchestrator.models.generate(f"Execute: {step_goal}")

            res = self.orchestrator.executor.execute(task)
            results.append({"step": step.get("step"), "goal": step.get("goal"), "result": res})

        return {**data, "results": results}

    def _memory_stage(self, data: dict):
        """DEPRECATED: isolated for backwards compat only; never used by run_cycle."""
        # Record plan and results into episodic memory
        event = {"prompt": data.get("prompt"), "plan": data.get("plan"), "results": data.get("results")}
        try:
            self.orchestrator.memory.remember_event(event)
        except Exception:
            # best-effort
            pass

        return {**data, "stored": True}

    ##################################################
    # PLAN
    ##################################################

    def create_plan(

        self,

        goal,

    ):

        if hasattr(self.authoritative_planner, "create_plan"):
            return self.authoritative_planner.create_plan(goal, [str(goal)])
        return self.planner.create(goal)

    ##################################################
    # REASON
    ##################################################

    def reason(

        self,

        problem,

    ):

        if self.authoritative_reasoner is not None:
            try:
                return self.authoritative_reasoner.think(str(problem))
            except Exception:
                pass
        return self.reasoning.reason(problem)

    ##################################################
    # DECISION
    ##################################################

    def decide(

        self,

        options,

    ):

        return self.authoritative_decision.choose(options)

    ##################################################
    # LEARN
    ##################################################

    def learn(

        self,

        lesson,

    ):

        self.learning.learn(

            lesson,

        )

        self.intelligence.learn()

    ##################################################
    # REFLECT
    ##################################################

    def reflect(

        self,

        result,

    ):

        return self.reflection.reflect(

            result,

        )

    ##################################################
    # EXECUTE
    ##################################################

    def execute(

        self,

        route,

        *args,

        **kwargs,

    ):

        return self.orchestrator.execute(

            route,

            *args,

            **kwargs,

        )

    ##################################################
    # STATUS
    ##################################################

    def health(self):

        """Executive status without private chain-of-thought.

        Exposes lifecycle state, focus summary, goal counts, intelligence
        metrics, and recent consciousness transitions — never raw prompts,
        reasoning traces, or model internals.
        """
        history = getattr(self.consciousness, "state_history", []) or []
        return {

            "running": self.running,

            "state": self.consciousness.get_state(),

            "focus": self.consciousness.current_focus(),

            "recent_states": [h.get("state") for h in history[-8:]],

            "transitions": len(history),

            "active_goals": len(

                self.goals.active_goals()

            ),

            "completed_goals": len(

                self.goals.completed_goals()

            ),

            "intelligence": self.intelligence.intelligence_score(),

            "canonical_path": list(self.canonical_execution_path),

        }

    ##################################################
    # RESET
    ##################################################

    def reset(self):

        self.consciousness.clear()

        self.learning.clear()

        self.planner.reset()

        self.goals.clear()

        self.running = False

    ##################################################
    # FUTURE FEATURES
    ##################################################

    def autonomous_cycle(self):
        """
        Future:
        Autonomous reasoning cycle.
        """
        pass

    ##################################################

    def self_improvement(self):
        """
        Future:
        Improve architecture.
        """
        pass

    ##################################################

    def recursive_reasoning(self):
        """
        Future:
        Multi-stage reasoning.
        """
        pass

    ##################################################

    def world_model(self):
        """
        Future:
        Internal world simulation.
        """
        pass

    ##################################################

    def emotional_intelligence(self):
        """
        Future:
        Emotion modeling.
        """
        pass

    ##################################################

    def self_awareness(self):
        """
        Future:
        Self-awareness systems.
        """
        pass

    ##################################################

    def dream(self):
        """
        Future:
        Offline learning cycle.
        """
        pass
