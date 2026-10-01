from __future__ import annotations
"""Generic environment learning (6U §12): observe -> hypothesize -> act ->
observe change -> update world model -> test -> retain validated rule.

Task-structure agnostic (works for unfamiliar interactive tasks incl.
ARC-style grids). Hypotheses carry support/refutation counts; only
rules surviving a confirmation test are retained.
"""

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class Hypothesis:
    text: str
    support: int = 0
    refuted: int = 0
    confirmed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EnvironmentLearner:
    """State-transition tracker + hypothesis tester for one episode."""

    def __init__(self, max_steps: int = 20):
        self.max_steps = max_steps
        self.transitions: List[Dict[str, Any]] = []
        self.hypotheses: List[Hypothesis] = []
        self.rules: List[str] = []
        self.failed: List[str] = []
        # Entity tracker (7J): per-key last-seen value + change counts.
        self.entities: Dict[str, Dict[str, Any]] = {}

    def track_entities(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Update entity ledger from an observation. Returns changed keys."""
        changed = {}
        for key, value in state.items():
            entry = self.entities.get(key)
            if entry is None:
                self.entities[key] = {"value": value, "seen": 1,
                                      "changes": 0}
            else:
                entry["seen"] += 1
                if entry["value"] != value:
                    entry["value"] = value
                    entry["changes"] += 1
                    changed[key] = value
        return changed

    def rule_confidence(self, rule: str) -> float:
        """support / (support + refuted) over hypotheses backing a rule."""
        sup = ref = 0
        for hyp in self.hypotheses:
            if hyp.text == rule:
                sup += hyp.support
                ref += hyp.refuted
        return round(sup / max(1, sup + ref), 3)

    def observe(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return dict(state)

    def hypothesize(self, text: str) -> Hypothesis:
        hyp = Hypothesis(text=text)
        self.hypotheses.append(hyp)
        return hyp

    def step(self, before: Dict[str, Any], action: Dict[str, Any],
             after: Dict[str, Any]) -> Dict[str, Any]:
        delta = {k: {"before": before.get(k), "after": after.get(k)}
                 for k in set(before) | set(after)
                 if before.get(k) != after.get(k)}
        record = {"action": dict(action), "delta": delta,
                  "t": round(time.perf_counter(), 3)}
        self.transitions.append(record)
        return record

    def confirm(self, hyp: Hypothesis,
                test: Callable[[], bool]) -> bool:
        """Run one confirmation test; retain the rule iff it passes."""
        try:
            ok = bool(test())
        except Exception:
            ok = False
        if ok:
            hyp.support += 1
            hyp.confirmed = True
            if hyp.text not in self.rules:
                self.rules.append(hyp.text)
        else:
            hyp.refuted += 1
            if hyp.text not in self.failed:
                self.failed.append(hyp.text)
        return ok

    def run_episode(self, sense: Callable[[], Dict[str, Any]],
                    propose: Callable[[Dict[str, Any], List[Hypothesis]], Dict[str, Any]],
                    do: Callable[[Dict[str, Any]], Dict[str, Any]],
                    solved: Callable[[Dict[str, Any]], bool]) -> Dict[str, Any]:
        """Full observe/act loop until solved or step budget exhausts."""
        state = self.observe(sense())
        self.track_entities(state)
        for _ in range(self.max_steps):
            if solved(state):
                return {"solved": True, "steps": len(self.transitions),
                        "rules": list(self.rules),
                        "entities": {k: dict(v) for k, v in self.entities.items()}}
            action = propose(dict(state), list(self.hypotheses))
            after = self.observe(do(dict(action)))
            self.step(state, action, after)
            self.track_entities(after)
            state = after
        return {"solved": bool(solved(state)), "steps": len(self.transitions),
                "rules": list(self.rules),
                "entities": {k: dict(v) for k, v in self.entities.items()}}
