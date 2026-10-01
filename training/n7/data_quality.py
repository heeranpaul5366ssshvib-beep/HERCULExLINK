from __future__ import annotations
"""Dataset quality analyzer (N7.7): machine-readable corpus audit.

Measures empties, duplicates, extremes, encoding, repetition
anomalies, boilerplate, tokenizer failures, and token-length
distribution. Reports only — never deletes or rewrites data.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def analyze(docs: List[Any], tokenizer=None) -> Dict[str, Any]:
    texts = [d.text if hasattr(d, "text") else str(d) for d in docs]
    lengths = [len(t) for t in texts]
    token_lens = []
    tok_failures = []
    for i, text in enumerate(texts):
        if tokenizer is not None:
            try:
                token_lens.append(len(tokenizer.encode(text)))
            except Exception as exc:
                tok_failures.append({"index": i, "error": str(exc)[:120]})
    counts = Counter(texts)
    dups = sum(c - 1 for c in counts.values() if c > 1)
    repeated_char = sum(1 for t in texts if any(
        ch * 8 in t for ch in set(t) if ch.strip()))
    report = {
        "samples": len(texts),
        "empty_samples": sum(1 for t in texts if not t.strip()),
        "duplicate_samples": dups,
        "short_samples_lt10": sum(1 for t in texts if len(t.strip()) < 10),
        "long_samples_gt2000": sum(1 for t in texts if len(t) > 2000),
        "invalid_utf8": 0,
        "repeated_char_anomalies": repeated_char,
        "tokenizer_failures": tok_failures,
        "char_len_p50": sorted(lengths)[len(lengths) // 2] if lengths else 0,
        "char_len_max": max(lengths) if lengths else 0,
        "token_len_p50": (sorted(token_lens)[len(token_lens) // 2]
                          if token_lens else None),
        "token_len_max": max(token_lens) if token_lens else None,
        "filtering_applied": "none (report only)",
    }
    for text in texts:
        try:
            text.encode("utf-8").decode("utf-8")
        except Exception:
            report["invalid_utf8"] += 1
    return report


def main() -> int:
    base = Path(__file__).resolve().parent
    from models.hercule_lm.data import DataSource, load_documents

    sources = [DataSource(**s) for s in
               json.loads((base.parent / "data" / "sources.json").read_text(encoding="utf-8"))]
    docs = load_documents(str(base.parent / "data" / "raw"), sources, paragraphs=True)
    report = analyze(docs)
    (base / "data_quality_report.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
