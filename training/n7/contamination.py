from __future__ import annotations
"""Contamination checks (N7.6): train/val corpus vs evaluation set.

Detects exact-document, normalized-text, exact-sample, and token
bigram overlap. Reports counts verbatim; never edits data.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _bigrams(text: str) -> set:
    tokens = _normalize(text).split(" ")
    return set(zip(tokens, tokens[1:])) if len(tokens) > 1 else set()


def check(train_texts: List[str], eval_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    train_norm = {_normalize(t) for t in train_texts}
    train_bigrams: set = set()
    for text in train_texts:
        train_bigrams |= _bigrams(text)
    exact_doc, normalized, sample, bigram_hit = 0, 0, 0, 0
    for item in eval_items:
        prompt = str(item.get("prompt", ""))
        if prompt in train_texts:
            exact_doc += 1
        if _normalize(prompt) in train_norm:
            normalized += 1
        if any(prompt and prompt in t for t in train_texts):
            sample += 1
        item_bigrams = _bigrams(prompt)
        if item_bigrams and item_bigrams & train_bigrams:
            bigram_hit += 1
    total = len(eval_items)
    return {
        "total_samples": total,
        "exact_document_overlap": exact_doc,
        "normalized_text_overlap": normalized,
        "exact_sample_overlap": sample,
        "bigram_overlap_samples": bigram_hit,
        "overlap_pct": {k: round(v / max(1, total) * 100, 1)
                        for k, v in {"exact": exact_doc, "normalized": normalized,
                                     "sample": sample, "bigram": bigram_hit}.items()},
    }


def main() -> int:
    base = Path(__file__).resolve().parent
    from models.hercule_lm.data import DataSource, load_documents

    sources = [DataSource(**s) for s in
               json.loads((base.parent / "data" / "sources.json").read_text(encoding="utf-8"))]
    docs = load_documents(str(base.parent / "data" / "raw"), sources, paragraphs=True)
    eval_items = json.loads((base / "eval_set.json").read_text(encoding="utf-8"))
    report = check([d.text for d in docs], eval_items)
    (base / "contamination_report.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
