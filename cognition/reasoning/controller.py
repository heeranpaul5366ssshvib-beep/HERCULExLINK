from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Adaptive Reasoning Controller (v2 Phase 4)
Author: Heeran Paul
License: MIT
--------------------------------------------

Decides HOW MUCH reasoning each request deserves — deterministically,
inspectably, and boundedly. The model never sets its own compute
budget; this controller does, from complexity + risk signals, and the
budget is enforced outside the model (token caps, timeouts, pass
limits). Reasoning depth is independent of authorization: deeper
reasoning never grants permissions, skips validation, or widens tool
limits.

Pipeline position::

    REQUEST -> CLASSIFICATION -> COMPLEXITY/RISK -> REASONING MODE
        -> MODEL ROUTING -> REASONING (budgeted) -> PLAN/RESPONSE

Reuses Reasoner, DecisionEngine, ModelRouter/ModelManager, Planner,
memory, experience, and the world model. Creates no duplicate
reasoning manager.
"""

import re
import time
from typing import Any, Dict, List, Optional

MODES = ("DETERMINISTIC", "LIGHT", "STANDARD", "DEEP", "EXPERT")

_BUDGETS: Dict[str, Dict[str, Any]] = {
    "DETERMINISTIC": {"max_tokens": 0, "timeout_s": 0,
                      "max_passes": 0, "max_context_chars": 0,
                      "max_tool_calls": 0},
    "LIGHT": {"max_tokens": 64, "timeout_s": 15,
              "max_passes": 1, "max_context_chars": 800,
              "max_tool_calls": 4},
    "STANDARD": {"max_tokens": 256, "timeout_s": 30,
                 "max_passes": 1, "max_context_chars": 1500,
                 "max_tool_calls": 8},
    "DEEP": {"max_tokens": 384, "timeout_s": 60,
             "max_passes": 2, "max_context_chars": 2000,
             "max_tool_calls": 12},
    "EXPERT": {"max_tokens": 512, "timeout_s": 90,
               "max_passes": 4, "max_context_chars": 2500,
               "max_tool_calls": 16},
}

_CLAUSE_RE = re.compile(r"[,;]|\band\b|\bthen\b", re.IGNORECASE)
_CODE_RE = re.compile(r"(?i)\b(code|function|class|debug|refactor|implement|script|program|bug|compile|test suite|pytest)\b")
_MATH_RE = re.compile(r"\d")
_ANAPHORA_RE = re.compile(r"(?i)\b(it|that|they|them)\b")
_WORLD_RE = re.compile(r"(?i)\b(running|earlier|previous|used earlier|last session|what is on|on my screen)\b")
_MULTI_ACTION_RE = re.compile(r"(?i)\b(then|and then|after that|followed by|verify it|read it back)\b")
_HIGH_RISK_RE = re.compile(
    r"(?i)\b(delete|remove all|format|uninstall|install|registry|password|credential|"
    r"admin|shutdown|reboot|send |submit|payment|rm -rf|del /|mkfs)\b")
_COMPUTER_RE = re.compile(
    r"(?i)\b(click|double click|right click|type into|press |hotkey|move the (pointer|mouse)|"
    r"screenshot|open notepad|open calculator)\b")


def _clauses(text: str) -> List[str]:
    return [c.strip() for c in _CLAUSE_RE.split(str(text or "")) if c.strip()]


class ComplexityAssessment(Dict[str, Any]):
    """Deterministic assessment (dict with a fixed schema)."""


def assess_complexity(text: str, capabilities: Optional[List[str]] = None,
                      context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Inspectable complexity signals (no model call, ever)."""
    lowered = str(text or "").lower()
    caps = [str(c).upper() for c in (capabilities or [])]
    clauses = _clauses(text)
    actions = len(re.findall(r"(?i)\b(create|write|read|run|open|click|type|calculate|verify|check|make|send)\b",
                             lowered))
    digits = len(_MATH_RE.findall(lowered))
    operators = len(re.findall(r"[+\-*/^%]", lowered))
    signals: Dict[str, Any] = {
        "length": len(str(text or "")),
        "clauses": len(clauses),
        "actions": actions,
        "capabilities": caps,
        "capability_count": len(set(caps)),
        "ambiguous": bool(_ANAPHORA_RE.search(lowered)),
        "multi_step": bool(_MULTI_ACTION_RE.search(lowered)) or len(clauses) >= 3,
        "code": bool(_CODE_RE.search(lowered)),
        "math_digits": digits,
        "math_operators": operators,
        "math_complex": digits >= 4 or operators >= 3,
        "world_ref": bool(_WORLD_RE.search(lowered)),
        "dependencies": max(0, len(clauses) - 1),
    }
    prior_failures = 0
    try:
        failures = (context or {}).get("recent_failures", 0)
        prior_failures = int(failures or 0)
    except (TypeError, ValueError):
        prior_failures = 0
    signals["prior_failures"] = prior_failures
    score = 0
    score += min(3, len(clauses) // 2)
    score += min(3, actions // 2)
    score += min(2, len(set(caps)))
    if signals["ambiguous"]:
        score += 2
    if signals["code"]:
        score += 2
    if signals["math_complex"]:
        score += 1
    if signals["multi_step"]:
        score += 2
    if len(str(text or "")) > 300:
        score += 2
    elif len(str(text or "")) > 120:
        score += 1
    score += min(3, prior_failures)
    if signals["world_ref"]:
        score = max(0, score - 1)  # structured state may short-circuit
    signals["score"] = score
    return signals


def assess_risk(text: str, capabilities: Optional[List[str]] = None) -> Dict[str, Any]:
    """Risk tier, kept separate from reasoning depth."""
    lowered = str(text or "").lower()
    caps = [str(c).upper() for c in (capabilities or [])]
    try:
        from cognition.capabilities.capability import CAPABILITY_RISK

        levels = []
        for cap in caps:
            try:
                from cognition.capabilities.capability import coerce_capability

                raw = CAPABILITY_RISK.get(coerce_capability(cap), "LOW")
                levels.append(str(getattr(raw, "value", raw)).upper())
            except Exception:
                levels.append("LOW")
    except Exception:
        levels = ["LOW"]
    signals = {"capability_risk": max(levels, key=["LOW", "MEDIUM", "HIGH"].index)
               if levels else "LOW",
               "high_pattern": bool(_HIGH_RISK_RE.search(lowered)),
               "computer": bool(_COMPUTER_RE.search(lowered))}
    if signals["high_pattern"] or "HIGH" in levels:
        tier = "HIGH"
    elif signals["computer"] or "MEDIUM" in levels:
        tier = "MEDIUM"
    else:
        tier = "LOW"
    signals["tier"] = tier
    return signals


def select_mode(complexity: Dict[str, Any], risk: Dict[str, Any],
                is_question: bool = False) -> Dict[str, str]:
    """Mode table (deterministic, inspectable)."""
    score = int(complexity.get("score", 0) or 0)
    caps = complexity.get("capabilities", []) or []
    n_caps = len(set(caps))
    short = int(complexity.get("length", 0) or 0) <= 120
    single_action = int(complexity.get("actions", 0) or 0) <= 1
    tier = risk.get("tier", "LOW")
    # Fast path: simple capability work, low risk, no ambiguity.
    if (caps and tier == "LOW" and single_action and short
            and not complexity.get("ambiguous") and not is_question):
        return {"mode": "DETERMINISTIC",
                "reason": f"simple deterministic: {sorted(set(caps))}"}
    # Light path: short conversational requests.
    if is_question and short and score <= 2 and tier == "LOW":
        return {"mode": "LIGHT", "reason": "short conversational request"}
    # Expert: very hard, or hard with a failure history. High risk
    # alone escalates to DEEP (below), never straight to EXPERT.
    if score >= 11 or (score >= 8
                       and int(complexity.get("prior_failures", 0) or 0) >= 2):
        return {"mode": "EXPERT",
                "reason": f"hard request (score={score}, risk={tier})"}
    # Deep: multi-intent, ambiguity, code, complexity, or failure history.
    if (score >= 5 or (n_caps >= 2 and int(complexity.get("clauses", 0) or 0) >= 2)
            or complexity.get("ambiguous") or complexity.get("code")
            or int(complexity.get("prior_failures", 0) or 0) >= 1
            or tier == "HIGH"):
        return {"mode": "DEEP",
                "reason": f"complex request (score={score}, risk={tier})"}
    return {"mode": "STANDARD", "reason": f"normal request (score={score})"}


class AdaptiveReasoningController:
    """Mode selection + budgeted model routing (no duplicate manager)."""

    def __init__(self, models: Any = None):
        # ``models`` is a ModelManager (or a stub with list_models/
        # default_model/generate). None = assessment-only mode.
        self.models = models
        self.last_decision: Dict[str, Any] = {}
        self.last_latency_ms: float = 0.0

    # --------------------------------------------------
    # Model inventory (installed/available only)
    # --------------------------------------------------
    def inventory(self) -> List[Dict[str, Any]]:
        """Installed models with size/thinking metadata (never invented)."""
        models = self.models
        if models is None:
            return []
        items: List[Dict[str, Any]] = []
        try:
            if hasattr(models, "installed_builtin_models"):
                for model_id in models.installed_builtin_models() or []:
                    items.append({"id": str(model_id), "provider": "builtin",
                                  "size": 0, "thinking": False,
                                  "context": 4096, "capabilities": ["chat"]})
        except Exception:
            pass
        try:
            ollama = getattr(getattr(models, "router", None), "adapters", {}).get("ollama")
            details = []
            if ollama is not None and hasattr(ollama, "client"):
                try:
                    details = ollama.client.model_details() or []
                except Exception:
                    details = []
            names = []
            try:
                names = list(models.installed_ollama_models() or [])
            except Exception:
                names = []
            by_name = {str(d.get("name", "")): d for d in details if isinstance(d, dict)}
            for name in names:
                info = by_name.get(name, {})
                caps = [str(c).lower() for c in (info.get("capabilities", []) or [])]
                detail = info.get("details", {}) if isinstance(info.get("details"), dict) else {}
                try:
                    size = int(info.get("size", 0) or 0)
                except (TypeError, ValueError):
                    size = 0
                try:
                    context = int(detail.get("context_length", 0) or 0) or 8192
                except (TypeError, ValueError):
                    context = 8192
                items.append({"id": name, "provider": "ollama", "size": size,
                              "thinking": "thinking" in caps, "context": context,
                              "capabilities": caps or ["chat"]})
        except Exception:
            pass
        try:
            builtin_sizes = {}
            from models.builtin import model_manager as _store

            for meta in _store.list_installed():
                builtin_sizes[str(meta.get("id", ""))] = int(meta.get("size", 0) or 0)
            for item in items:
                if item["provider"] == "builtin" and item["id"] in builtin_sizes:
                    item["size"] = builtin_sizes[item["id"]]
                    # UAI Phase N2: models at/above 1 GB carry the
                    # reasoning profile (evidence-gated by evaluation);
                    # smaller ones stay chat/classification only.
                    if int(item["size"] or 0) >= 750000000 and "reasoning" not in item["capabilities"]:
                        item["capabilities"] = list(item["capabilities"]) + ["reasoning"]
        except Exception:
            pass
        # Include mock adapter when explicitly allowed (tests/dev)
        try:
            allow_mock = getattr(models, "allow_mock_fallback", False)
            if allow_mock:
                router = getattr(models, "router", None)
                if router is not None:
                    mock_adapter = router._get_adapter("mock")  # force init
                    if mock_adapter is not None:
                        items.append({"id": "mock", "provider": "mock", "size": 0,
                                      "thinking": False, "context": 4096, "capabilities": ["chat", "testing"]})
        except Exception:
            pass
        seen, ordered = set(), []
        for item in items:
            if item["id"] not in seen:
                seen.add(item["id"])
                ordered.append(item)
        return ordered

    def _preferred_provider(self) -> str:
        try:
            return str(getattr(self.models, "provider_pref", "auto") or "auto")
        except Exception:
            return "auto"

    def select_model(self, mode: str,
                     inventory: Optional[List[Dict[str, Any]]] = None
                     ) -> Dict[str, Any]:
        """Smallest-suitable-installed-model routing (honest when empty)."""
        pool = list(inventory if inventory is not None else self.inventory())
        if not pool:
            return {"model": "", "provider": "", "reason": "no models installed"}
        pref = self._preferred_provider()
        if pref in ("builtin", "ollama"):
            pool = [m for m in pool if m["provider"] == pref] or pool
        default_id = ""
        try:
            default_id = str(getattr(self.models, "default_model", "") or "")
        except Exception:
            default_id = ""
        by_size = sorted(pool, key=lambda m: (int(m.get("size", 0) or 0),
                                              str(m.get("id", ""))))
        thinkers = [m for m in pool if m.get("thinking")]
        if mode == "LIGHT":
            small = by_size[0]
            return {"model": small["id"], "provider": small["provider"],
                    "reason": "smallest installed model"}
        if mode in ("DEEP", "EXPERT"):
            if thinkers:
                best = sorted(thinkers, key=lambda m: int(m.get("size", 0) or 0),
                              reverse=True)[0]
                return {"model": best["id"], "provider": best["provider"],
                        "reason": "thinking-capable model"}
            big = by_size[-1]
            return {"model": big["id"], "provider": big["provider"],
                    "reason": "largest installed model"}
        if default_id and any(m["id"] == default_id for m in pool):
            provider = next(m["provider"] for m in pool if m["id"] == default_id)
            return {"model": default_id, "provider": provider,
                    "reason": "configured default model"}
        mid = by_size[len(by_size) // 2]
        return {"model": mid["id"], "provider": mid["provider"],
                "reason": "median installed model"}

    # --------------------------------------------------
    # Decide (assessment + experience promotion + shortcut)
    # --------------------------------------------------
    def decide(self, text: str, context: Optional[Dict[str, Any]] = None,
               is_question: bool = False,
               capabilities: Optional[List[str]] = None) -> Dict[str, Any]:
        """Full reasoning decision (deterministic, budgeted, inspectable)."""
        context = dict(context or {})
        caps = list(capabilities or [])
        if not caps:
            try:
                from cognition.capabilities.inference import infer_capabilities

                caps = [c.value for c in infer_capabilities(text)]
            except Exception:
                caps = []
        complexity = assess_complexity(text, caps, context)
        risk = assess_risk(text, caps)
        # World-model shortcut: verified structured state can answer
        # without any model call (mode stays DETERMINISTIC).
        shortcut = ""
        world_answer = ""
        resolver = context.get("world_resolver")
        if resolver is not None and hasattr(resolver, "answer"):
            try:
                verdict = resolver.answer(text)
                if (isinstance(verdict, dict)
                        and verdict.get("status") == "answered"
                        and any((e or {}).get("verified") for e in
                                verdict.get("evidence", []) or [])):
                    shortcut = "world"
                    world_answer = str(verdict.get("answer", ""))[:300]
            except Exception:
                shortcut, world_answer = "", ""
        picked = select_mode(complexity, risk, is_question=bool(is_question or shortcut))
        mode = picked["mode"]
        reason = picked["reason"]
        # Experience-aware promotion (bounded, per-request, never persisted):
        # repeated failures on these capabilities deserve deeper reasoning.
        try:
            stats = dict(context.get("experience_stats", {}) or {})
            fails = int(context.get("recent_failures", 0) or 0)
            weak = [c for c in set(caps)
                    if float(stats.get(str(c).upper(), 1.0)) < 0.5]
            if (weak or fails >= 2) and mode in ("LIGHT", "STANDARD", "DEEP"):
                order = ["LIGHT", "STANDARD", "DEEP", "EXPERT"]
                if mode == "LIGHT" and not is_question:
                    mode = "STANDARD"
                elif mode in ("STANDARD", "DEEP"):
                    mode = order[min(3, order.index(mode) + 1)]
                reason += f" + experience promotion (weak={weak or fails})"
        except Exception:
            pass
        if shortcut:
            mode, reason = "DETERMINISTIC", "world-model verified answer"
        routed = self.select_model(mode)
        budget = dict(_BUDGETS.get(mode, _BUDGETS["STANDARD"]))
        decision = {"mode": mode, "model": routed.get("model", ""),
                    "provider": routed.get("provider", ""),
                    "reason": f"{reason}; model: {routed.get('reason', '')}",
                    "budget": budget, "risk": risk.get("tier", "LOW"),
                    "risk_signals": {k: v for k, v in risk.items() if k != "tier"},
                    "complexity": complexity.get("score", 0),
                    "signals": {k: v for k, v in complexity.items() if k != "score"},
                    "capabilities": caps, "shortcut": shortcut,
                    "world_answer": world_answer}
        self.last_decision = decision
        return decision

    # --------------------------------------------------
    # Budgeted reasoning (passes capped, summaries only)
    # --------------------------------------------------
    def reason_budgeted(self, prompt: str, decision: Optional[Dict[str, Any]] = None,
                        system: str = "") -> Dict[str, Any]:
        """Run bounded passes under the decision budget (no CoT stored)."""
        started = time.perf_counter()
        decision = dict(decision or self.last_decision or {})
        mode = str(decision.get("mode", "STANDARD"))
        budget = dict(decision.get("budget", {}) or _BUDGETS["STANDARD"])
        model = str(decision.get("model", "") or "")
        passes = max(1, min(4, int(budget.get("max_passes", 1) or 1)))
        timeout_s = float(budget.get("timeout_s", 30) or 30)
        max_tokens = int(budget.get("max_tokens", 256) or 256)
        if self.models is None:
            return {"status": "failed", "error": "no model backend bound",
                    "mode": mode, "passes": 0}
        if not str(decision.get("model", "") or ""):
            return {"status": "failed",
                    "error": "no model installed for mode "
                             f"{mode} (honest unavailable)",
                    "mode": mode, "passes": 0}
        if mode == "DETERMINISTIC" or max_tokens <= 0:
            return {"status": "skipped", "mode": mode, "passes": 0,
                    "summary": "", "reason": "deterministic path needs no model"}
        outputs: List[str] = []
        per_pass_timeout = max(5.0, timeout_s / max(1, passes))
        status, error = "completed", ""
        for index in range(passes):
            if index == 0:
                task_prompt = f"Understand and reason concisely:\n{prompt}"
            elif index == passes - 1 and passes > 1:
                task_prompt = ("Validate and finalize (one short paragraph, "
                               f"no reasoning trace):\n{outputs[-1][:500]}")
            else:
                task_prompt = (f"Solve stepwise, keep it brief:\n{prompt}\n"
                               f"Context: {outputs[-1][:500] if outputs else ''}")
            try:
                generate = getattr(self.models, "generate")
                try:
                    text = generate(task_prompt, model=model or None,
                                    timeout_s=per_pass_timeout,
                                    options={"num_predict": max_tokens},
                                    max_tokens=max_tokens)
                except TypeError:
                    text = generate(task_prompt, model=model or None)
            except Exception as exc:
                status, error = "failed", str(exc)[:300]
                break
            if isinstance(text, str) and text.startswith("[HERCULE Error]"):
                status, error = "failed", text[:300]
                break
            outputs.append(str(text or "")[:1000])
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        self.last_latency_ms = elapsed_ms
        if status != "completed" or not outputs:
            return {"status": status or "failed",
                    "error": error or "empty model output",
                    "mode": mode, "passes": len(outputs),
                    "latency_ms": elapsed_ms}
        return {"status": "completed", "mode": mode, "passes": len(outputs),
                "summary": outputs[-1][:500], "latency_ms": elapsed_ms,
                "model": model}

    # --------------------------------------------------
    # Strategy choice via the existing DecisionEngine
    # --------------------------------------------------
    def choose_strategy(self, strategies: List[Dict[str, Any]],
                        experience_stats: Optional[Dict[str, Any]] = None
                        ) -> Dict[str, Any]:
        """Score candidate reasoning strategies (policy-independent).

        Each strategy: {"mode", "latency_s", "model_available",
        "verification"("strong"|"weak"), "risk"}. Scores expected
        success, latency, availability, verification ease, and risk —
        then delegates the argmax to DecisionEngine.choose. Never
        authorizes anything.
        """
        from cognition.decision.decision_engine import DecisionEngine

        stats = dict(experience_stats or {})
        options, scores, reasons = [], [], []
        for strategy in strategies or []:
            mode = str(strategy.get("mode", "STANDARD"))
            if mode not in MODES:
                continue
            depth = MODES.index(mode)
            expected = float(stats.get(mode, 0.7))
            latency = float(strategy.get("latency_s", 5.0 * (depth + 1)) or 0.0)
            available = 1.0 if strategy.get("model_available", True) else 0.0
            verify = 1.0 if str(strategy.get("verification", "")).lower() == "strong" else 0.4
            risk_pen = 1.0 if str(strategy.get("risk", "LOW")).upper() == "HIGH" else 0.0
            score = (3.0 * expected - 0.05 * min(60.0, latency)
                     + 2.0 * available + 1.0 * verify - 1.5 * risk_pen)
            options.append(strategy)
            scores.append(round(score, 3))
            reasons.append(f"{mode}: success={expected} latency={latency}s "
                           f"avail={available} verify={verify} riskpen={risk_pen}")
        if not options:
            return {"choice": None, "scores": [], "reasons": ["no valid strategy"]}
        choice = DecisionEngine().choose(options, scores)
        return {"choice": choice, "scores": scores, "reasons": reasons}
