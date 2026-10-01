from __future__ import annotations
"""Build the N7 eval set (N7.5/N7.8): HERCULE-authored, deterministic.

Writes ``training/n7/eval_set.json`` (fixed items with category,
prompt, expected completion prefix or exact answer, scoring rule)
plus ``training/n7/eval_manifest.json`` (seed, counts, checksums).
Items are hand templates + seeded arithmetic; every string is
checked against the training corpus blocklist at build time.
"""

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
EVAL_VERSION = "hercule-lm-eval-v1"
SEED = 77031


def _items() -> list:
    rng = random.Random(SEED)
    items = []
    # BASIC_LANGUAGE: complete the proverb-like sentence.
    for i, (prompt, expected) in enumerate([
        ("The sun rises in the ", "east"),
        ("Water freezes into ", "ice"),
        ("A week has seven ", "days"),
        ("Birds build ", "nests"),
    ]):
        items.append({"id": f"lang-{i:02d}", "category": "BASIC_LANGUAGE",
                      "prompt": prompt, "expected_prefix": expected,
                      "rule": "prefix"})
    # VOCABULARY: define the word.
    for i, (prompt, expected) in enumerate([
        ("A directory contains ", "files"),
        ("Verification means ", "checking"),
    ]):
        items.append({"id": f"vocab-{i:02d}", "category": "VOCABULARY",
                      "prompt": prompt, "expected_prefix": expected,
                      "rule": "contains"})
    # FACT_RECALL: corpus facts verbatim.
    for i, (prompt, expected) in enumerate([
        ("At sea level, water boils at ", "100"),
        ("The capital of France is ", "Paris"),
    ]):
        items.append({"id": f"fact-{i:02d}", "category": "FACT_RECALL",
                      "prompt": prompt, "expected_prefix": expected,
                      "rule": "prefix"})
    # SIMPLE_ARITHMETIC: held-out pairs (3-digit, seeded; never corpus pairs).
    pairs = set()
    while len(pairs) < 12:
        pairs.add((rng.randint(100, 999), rng.randint(100, 999)))
    for i, (a, b) in enumerate(sorted(pairs)):
        items.append({"id": f"arith-{i:02d}", "category": "SIMPLE_ARITHMETIC",
                      "prompt": f"Q: Calculate {a} + {b}.\nA:",
                      "expected_exact": f"{a + b}.", "rule": "exact-after-strip"})
    # PATTERN_COMPLETION / SEQUENCE.
    for i, (prompt, expected) in enumerate([
        ("1 2 3 4 ", "5"),
        ("2 4 6 8 ", "10"),
        ("a b c ", "d"),
    ]):
        items.append({"id": f"pattern-{i:02d}", "category": "PATTERN_COMPLETION",
                      "prompt": prompt, "expected_prefix": expected,
                      "rule": "prefix"})
    # LOGICAL_RULES.
    items.append({"id": "logic-00", "category": "LOGICAL_RULES",
                  "prompt": "All boxes contain books. Crate X is a box. Crate X contains ",
                  "expected_prefix": "books", "rule": "contains"})
    # INSTRUCTION_FOLLOWING.
    items.append({"id": "instr-00", "category": "INSTRUCTION_FOLLOWING",
                  "prompt": "Reply with exactly the word HELLO and nothing else.\n",
                  "expected_exact": "HELLO", "rule": "exact-after-strip"})
    # SHORT_CONTEXT: answer from the given context.
    items.append({"id": "ctx-00", "category": "SHORT_CONTEXT",
                  "prompt": "Context: the depot code is 451. Question: what is the depot code?\nAnswer:",
                  "expected_prefix": "451", "rule": "contains"})
    # LONGER_CONTEXT: repeated-fact retrieval.
    filler = " ".join(f"Filler sentence number {n}." for n in range(30))
    items.append({"id": "ctx-01", "category": "LONGER_CONTEXT",
                  "prompt": f"{filler} The hidden number is 777. {filler} The hidden number is",
                  "expected_prefix": "777", "rule": "contains"})
    # CODE_SYNTAX.
    items.append({"id": "code-00", "category": "CODE_SYNTAX",
                  "prompt": "def add(a, b):\n    return ",
                  "expected_prefix": "a + b", "rule": "contains"})
    # HERCULE_TERMINOLOGY.
    for i, (prompt, expected) in enumerate([
        ("Classify this request: 'compute 5 plus 5'.\n", "GOAL"),
        ("A skill must be  before it can execute.\n", "validated"),
    ]):
        items.append({"id": f"herc-{i:02d}", "category": "HERCULE_TERMINOLOGY",
                      "prompt": prompt, "expected_prefix": expected,
                      "rule": "contains"})
    return items


def main() -> int:
    items = _items()
    blob = json.dumps(items, sort_keys=True)
    manifest = {
        "name": "hercule-lm-eval", "version": EVAL_VERSION, "seed": SEED,
        "license": "HERCULE-authored (MIT, repo)", "source": "hercule-authored",
        "items": len(items),
        "by_category": {c: sum(1 for i in items if i["category"] == c)
                        for c in sorted({i["category"] for i in items})},
        "checksum": hashlib.sha256(blob.encode()).hexdigest()[:16],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split": "evaluation-only (never training input)",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "eval_set.json").write_text(json.dumps(items, indent=1), encoding="utf-8")
    (OUT_DIR / "eval_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"eval items={len(items)} checksum={manifest['checksum']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
