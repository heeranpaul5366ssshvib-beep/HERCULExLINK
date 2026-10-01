from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Planner
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from typing import Any, Dict, List, Optional


class Planner:
    """
    Creates execution plans for tasks.
    """

    def __init__(self):

        self.current_plan = []
        # Optional validated-skill source (UAI L1). None = legacy path
        # byte-identical. Only validated skills are ever consulted;
        # resolution never bypasses inference/validation/policy.
        self._skill_manager = None

    def configure_skills(self, skill_manager=None):
        """Attach a SkillManager for validated-skill consultation."""
        self._skill_manager = skill_manager
        return self

    def create_plan(
        self,
        goal: str,
        steps: list[str],
    ):

        if not steps:
            steps = [str(goal)]

        self.current_plan = [
            {
                "step": i + 1,
                "goal": str(goal),
                "description": step,
                "completed": False,
                "status": "pending",
            }
            for i, step in enumerate(steps)
        ]

        return self.current_plan

    def create(self, goal: str, steps: list[str] | None = None):
        steps = steps or [str(goal)]
        return self.create_plan(goal, steps)

    def configure_semantic(self, proposer=None, mode: str = "semantic_optional",
                           enabled: bool = False, **resolver_kwargs):
        """Configure model-backed capability resolution for this planner.

        Disabled by default: ``create_capable_plan`` keeps the legacy
        deterministic path byte-identically until explicitly enabled.
        ``resolver_kwargs`` (registry, policy, managers, environment,
        cache, context) build the hybrid resolver around ``proposer``.
        """
        self._semantic_proposer = proposer
        self._semantic_mode = mode
        self._semantic_enabled = enabled
        nested = resolver_kwargs.pop("resolver_kwargs", None)
        if isinstance(nested, dict):
            resolver_kwargs.update(nested)
        self._semantic_resolver_kwargs = dict(resolver_kwargs)
        return self

    def create_capable_plan(self, goal: str, steps: list | None = None,
                            semantic=None, proposer=None, chain: bool = False,
                            allow_skills: bool = False):
        """Capability-aware plan: WHAT + WHAT CAPABILITIES each step needs.

        ``semantic`` tri-state: None -> planner default (legacy
        deterministic unless configured); False -> legacy deterministic;
        True or a mode string -> hybrid resolution. The Planner remains
        authoritative; the proposer only suggests. ``create_plan``
        behavior is unchanged.

        ``allow_skills`` (goal-derived requests only — callers pass it
        only when ``steps`` was not explicitly supplied) lets a
        validated skill's procedure supply the step descriptions.
        Explicit caller steps always win; when no skill resolves, the
        legacy decomposition path runs byte-identically.
        """
        from cognition.planner.capable import build_capable_plan

        step_texts = steps or [str(goal)]
        # UAI L1: goal-derived plans (callers set ``allow_skills`` only
        # when no explicit steps were supplied) may adopt a validated
        # skill's procedure. Every skill-built step still flows through
        # capability inference, plan validation, tool matching,
        # policy, and verification downstream — skills advise, never
        # authorize.
        skill = self._resolve_skill(str(goal)) if allow_skills else None
        if skill is not None:
            proc = [str(p).strip() for p in (skill.procedure or [])
                    if str(p or "").strip()]
            caps = [str(c).upper() for c in (skill.required_capabilities or [])]
            step_texts = [{"description": p, "required_capabilities": caps}
                          for p in proc]
        resolver = self._semantic_resolver(semantic, proposer)
        self.current_plan = build_capable_plan(str(goal), step_texts, resolver=resolver, chain=chain)
        if skill is not None and step_texts:
            # Tag provenance; risk/verification were already derived
            # from the skill's declared capabilities by construction.
            for step in self.current_plan:
                step["skill_id"] = skill.skill_id
                step["skill_version"] = skill.version
        return self.current_plan

    def _resolve_skill(self, goal: str):
        """Best validated skill for a goal, or None (never raises)."""
        manager = getattr(self, "_skill_manager", None)
        if manager is None:
            return None
        try:
            skill = manager.resolve(goal)
        except Exception:
            return None
        if skill is None or not skill.is_registered():
            return None
        if not list(getattr(skill, "procedure", []) or []):
            return None
        return skill

    def plan_from_skill(self, goal: str) -> Optional[Dict[str, Any]]:
        """Validated-skill proposal for a goal (advisory, never executes).

        Returns {"skill_id", "version", "procedure", "capabilities"} or
        None. Callers still route the procedure through the normal
        validated pipeline.
        """
        skill = self._resolve_skill(str(goal or ""))
        if skill is None:
            return None
        proc = [str(p).strip() for p in (skill.procedure or [])
                if str(p or "").strip()]
        if not proc:
            return None
        return {"skill_id": skill.skill_id, "version": skill.version,
                "procedure": proc,
                "capabilities": [str(c).upper()
                                 for c in (skill.required_capabilities or [])]}

    def _semantic_resolver(self, semantic, proposer):
        """Build the hybrid step resolver or None for the legacy path."""
        if semantic is None:
            if not getattr(self, "_semantic_enabled", False):
                return None
            mode = getattr(self, "_semantic_mode", "semantic_optional")
            proposer = proposer if proposer is not None else getattr(self, "_semantic_proposer", None)
        elif semantic is False:
            return None
        elif semantic is True:
            mode = getattr(self, "_semantic_mode", "semantic_optional")
            proposer = proposer if proposer is not None else getattr(self, "_semantic_proposer", None)
        else:
            mode = str(semantic)
        from cognition.capabilities.hybrid import HybridMode, resolve_capabilities

        try:
            HybridMode(str(mode).lower())
        except ValueError:
            mode = "semantic_optional"
        kwargs = dict(getattr(self, "_semantic_resolver_kwargs", {}))

        def resolve(description, extra):
            context = ""
            if isinstance(extra, dict):
                context = str(extra.get("context", ""))
                explicit = extra.get("explicit_capabilities")
            else:
                explicit = None
            untrusted = ""
            if isinstance(extra, dict) and isinstance(extra.get("untrusted_content"), str):
                untrusted = extra["untrusted_content"]
            outcome = resolve_capabilities(
                {"description": description, "trusted": (extra.get("trusted", True) if isinstance(extra, dict) else True)},
                context=context, untrusted_content=untrusted, mode=mode,
                proposer=proposer, explicit_capabilities=explicit, **kwargs)
            return {"final": outcome.final, "optional": outcome.optional,
                    "report": outcome.as_dict()}

        return resolve

    def complete_step(
        self,
        index: int,
    ):

        if 0 <= index < len(self.current_plan):

            self.current_plan[index]["completed"] = True

    def pending_steps(self):

        return [
            step
            for step in self.current_plan
            if not step["completed"]
        ]

    def completed_steps(self):

        return [
            step
            for step in self.current_plan
            if step["completed"]
        ]

    def clear(self):

        self.current_plan.clear()