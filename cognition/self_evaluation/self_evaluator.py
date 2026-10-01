from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Self Evaluator
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class SelfEvaluator:

    def evaluate(
        self,
        response: str,
    ):

        score = 100

        if len(response) < 20:
            score -= 25

        return {

            "score": score,

            "passed": score >= 70,

        }

    def evaluate_task(self, report):
        """Structured post-task self-evaluation (deterministic, no model).

        Answers: goal satisfied? steps verified? replans? which abilities
        succeeded/failed? recovery required? reusable lesson? Input is the
        autonomous-loop completion report plus verification summary; the
        result is stored as experience, never executed.
        """
        report = dict(report or {})
        status = str(report.get("status", "failed")).lower()
        completed = list(report.get("completed", []) or [])
        failed = list(report.get("failed", []) or [])
        replans = int(report.get("replans", 0) or 0)
        verification = dict(report.get("verification", {}) or {})
        passed_steps = verification.get("passed_steps", len(completed))
        try:
            passed_steps = int(passed_steps)
        except (TypeError, ValueError):
            passed_steps = len(completed)
        failed_reasons = []
        for item in failed:
            if isinstance(item, dict):
                failed_reasons.append(str(item.get("reason") or item.get("detail", ""))[:200])
            else:
                failed_reasons.append(str(item)[:200])
        recovery_required = replans > 0 or status in ("partial", "failed")
        recovered = status in ("completed", "partial") and replans > 0
        goal_satisfied = status == "completed" and not failed
        # Stage 8 coverage metrics (all derived from the verified report).
        planned = report.get("planned_steps") or (len(completed) + len(failed))
        try:
            planned = int(planned)
        except (TypeError, ValueError):
            planned = len(completed) + len(failed)
        step_coverage = (len(completed) / planned) if planned else 0.0
        verification_coverage = (passed_steps / max(1, len(completed) + len(failed)))
        verification_coverage = min(1.0, max(0.0, verification_coverage))
        seen_descriptions: set = set()
        unnecessary_steps = 0
        for item in report.get("step_descriptions", []) or []:
            key = str(item or "").strip().lower()
            if key in seen_descriptions:
                unnecessary_steps += 1
            seen_descriptions.add(key)
        failed_assumptions = [r for r in failed_reasons if r]
        efficiency = 0.0
        if planned:
            efficiency = max(0.0, min(1.0, (passed_steps / planned)
                                      * (1.0 / (1 + replans))))
        abilities_succeeded = sorted({str(e.get("ability", "")) for e in
                                      [verification] if e.get("ability")})
        if goal_satisfied:
            lesson = (f"goal satisfied: {len(completed)} verified steps"
                      + (f" after {replans} replans" if replans else " first try"))
        elif recovered or status == "partial":
            lesson = (f"partial recovery: {len(completed)} steps verified, "
                      f"open failures: {'; '.join(failed_reasons)[:160]}")
        else:
            lesson = (f"goal unsatisfied: {'; '.join(failed_reasons)[:200] or 'no verified steps'}; "
                      f"replans used: {replans}")
        return {
            "goal_satisfied": goal_satisfied,
            "steps_verified": passed_steps,
            "steps_completed": len(completed),
            "steps_failed": len(failed),
            "replans": replans,
            "abilities_succeeded": abilities_succeeded,
            "failed_reasons": failed_reasons,
            "recovery_required": recovery_required,
            "recovered": recovered,
            "lesson": lesson[:300],
            "step_coverage": round(step_coverage, 3),
            "verification_coverage": round(verification_coverage, 3),
            "efficiency": round(efficiency, 3),
            "unnecessary_steps": unnecessary_steps,
            "failed_assumptions": failed_assumptions,
        }