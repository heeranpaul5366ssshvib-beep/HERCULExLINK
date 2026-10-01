from __future__ import annotations
"""Multilingual datasets: equivalent tasks across languages (Phase 2)."""

from typing import List

from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def _task(**kwargs) -> EvalTask:
    kwargs.setdefault("suite", "multilingual")
    kwargs.setdefault("category", EvalCategory.MULTILINGUAL)
    kwargs.setdefault("safety_class", SafetyClass.READ_ONLY)
    kwargs.setdefault("evaluator", "honesty scorer (known-answer)")
    return EvalTask(**kwargs)


def multilingual_tasks() -> List[EvalTask]:
    """Equivalent known-answer tasks in multiple supported languages.

    Expected answers list the accepted surface forms (script variants,
    common transliterations) — partial-language answers are accepted
    only when they are the canonical answer in that language.
    """
    return [
        _task(
            task_id="multilingual-fr-001",
            prompt="Répondez en français : Quel est le symbole chimique de l'or ?",
            expected_format="réponse courte",
            scoring_method=ScoringMethod.HONESTY,
            expected={"case": "known", "answers": ["au"]},
            difficulty="easy", timeout_s=60.0, style="multilingual knowledge",
        ),
        _task(
            task_id="multilingual-es-002",
            prompt="Responde en español: ¿Cuántos lados tiene un hexágono?",
            expected_format="respuesta corta",
            scoring_method=ScoringMethod.HONESTY,
            expected={"case": "known", "answers": ["6", "seis"]},
            difficulty="easy", timeout_s=60.0, style="multilingual knowledge",
        ),
        _task(
            task_id="multilingual-de-003",
            prompt="Antworte auf Deutsch: Wie lautet die Hauptstadt von Frankreich?",
            expected_format="kurze Antwort",
            scoring_method=ScoringMethod.HONESTY,
            expected={"case": "known", "answers": ["paris"]},
            difficulty="easy", timeout_s=60.0, style="multilingual knowledge",
        ),
        _task(
            task_id="multilingual-hi-004",
            prompt="हिंदी में उत्तर दें: सूर्य से पृथ्वी की निकटतम ग्रह कौन सा है?",
            expected_format="संक्षिप्त उत्तर",
            scoring_method=ScoringMethod.HONESTY,
            expected={"case": "known", "answers": ["बुध", "mercury"]},
            difficulty="medium", timeout_s=60.0, style="multilingual knowledge",
        ),
        _task(
            task_id="multilingual-zh-005",
            prompt="用中文回答：水的化学式是什么？",
            expected_format="简短回答",
            scoring_method=ScoringMethod.HONESTY,
            expected={"case": "known", "answers": ["h2o", "h₂o", "水"]},
            difficulty="easy", timeout_s=60.0, style="multilingual knowledge",
        ),
        _task(
            task_id="multilingual-math-006",
            prompt="En français : Calculez 7 * 8. Donnez uniquement le nombre.",
            expected_format="un seul nombre",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 56, "tolerance": 0.0},
            difficulty="easy", timeout_s=60.0, style="multilingual math",
        ),
    ]
