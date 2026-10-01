from __future__ import annotations
"""Research benchmark (UAI Phase M11): evidence, uncertainty, sources.

ResearchAbility executes through AbilityManager (real policy /
capability path) with per-task fixture sources — never the network,
never fabricated. Unavailable/empty sources must stay unverified.
"""

from typing import List

from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def _ability(task_id: str, topic: str, capabilities, expected: dict,
             difficulty: str, style: str, sources=None) -> EvalTask:
    extras = {"ability_eval": {"ability": "research", "task": topic,
                               "capabilities": list(capabilities)}}
    if sources is not None:
        extras["research_sources"] = list(sources)
    return EvalTask(
        task_id=task_id, category=EvalCategory.AGENTIC, suite="uai_research",
        prompt=f"Research: {topic}",
        expected_format="labeled evidence envelope",
        scoring_method=ScoringMethod.RESEARCH_EVIDENCE,
        expected=expected, evaluator="research evidence scorer",
        difficulty=difficulty, timeout_s=120.0,
        required_capabilities=list(capabilities),
        safety_class=SafetyClass.READ_ONLY, style=style,
        expected_behavior="labeled FACT/INFERENCE/HYPOTHESIS/UNCERTAINTY with sources",
        success_criteria="status and evidence honesty per spec",
        tags=["research"],
        extras=extras,
    )


def _src(url: str, content: str) -> dict:
    return {"url": url, "content": content}


def uai_research_tasks() -> List[EvalTask]:
    return [
        # FACT: two corroborating facts verify
        _ability("uai-research-fact-001", "alpha element compatibility",
                 ["KNOWLEDGE_RETRIEVAL"],
                 {"status": "verified", "min_evidence": 2},
                 "easy", "verified facts",
                 [_src("https://example.test/a", "[FACT] Alpha element present in release 3"),
                  _src("https://example.test/b", "[FACT] Beta element present in release 3")]),
        # MULTI-SOURCE: three sources, mixed labels
        _ability("uai-research-multi-002", "gamma protocol review",
                 ["KNOWLEDGE_RETRIEVAL"],
                 {"status": "unverified", "min_evidence": 3},
                 "medium", "multi-source synthesis",
                 [_src("https://example.test/a", "[FACT] Gamma spec ratified in March"),
                  _src("https://example.test/b", "Therefore adoption will follow quickly"),
                  _src("https://example.test/c", "plain field note with no markers")]),
        # CONFLICT: opposed facts flag contradiction, block verified
        _ability("uai-research-conflict-003", "delta support status",
                 ["KNOWLEDGE_RETRIEVAL"],
                 {"status": "unverified", "min_evidence": 2},
                 "medium", "conflict handling",
                 [_src("https://example.test/a", "[FACT] The library supports python 3.12"),
                  _src("https://example.test/b", "[FACT] The library does not support python 3.12")]),
        # UNAVAILABLE: no source attached → unverified, empty
        _ability("uai-research-unavail-004", "epsilon uncharted topic",
                 ["KNOWLEDGE_RETRIEVAL"],
                 {"status": "unverified", "min_evidence": 0},
                 "easy", "unavailable network honesty"),
        # EMPTY: source yields nothing → unverified, empty
        _ability("uai-research-empty-005", "zeta empty index",
                 ["KNOWLEDGE_RETRIEVAL"],
                 {"status": "unverified", "min_evidence": 0},
                 "easy", "empty result honesty", sources=[]),
        # UNCERTAINTY: single uncorroborated item stays uncertain
        _ability("uai-research-uncertain-006", "eta rumored feature",
                 ["KNOWLEDGE_RETRIEVAL"],
                 {"status": "unverified", "min_evidence": 1},
                 "medium", "uncertainty handling",
                 [_src("https://example.test/a", "Rumor suggests eta ships someday")]),
        # INFERENCE: reasoning-labeled content preserved
        _ability("uai-research-infer-007", "theta behavior study",
                 ["KNOWLEDGE_RETRIEVAL"],
                 {"status": "unverified", "min_evidence": 2},
                 "medium", "inference labeling",
                 [_src("https://example.test/a", "[FACT] Theta readings peak at noon"),
                  _src("https://example.test/b", "Thus theta output follows sunlight")]),
        # HYPOTHESIS: hedged content labeled, never upgraded
        _ability("uai-research-hypoth-008", "iota outlook memo",
                 ["KNOWLEDGE_RETRIEVAL"],
                 {"status": "unverified", "min_evidence": 1},
                 "hard", "hypothesis labeling",
                 [_src("https://example.test/a", "Results possibly suggest iota growth")]),
    ]
