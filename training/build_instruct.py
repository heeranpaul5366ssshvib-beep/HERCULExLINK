from __future__ import annotations
"""Build instruction/tool/code corpora (frontier P17-P20): fully
HERCULE-authored + deterministic synthetic, MIT. No web scraping,
no pretrained-model output, no user data. Eval prompts blocklisted.
"""

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "instruct"
SEED = 91042

BLOCKLIST = ["definitely_missing", "hercule_definitely_not_a_command",
             "rm -rf /", "win.ini", "eval_golden_", "Teleport",
             "admin password"]


def _clean(text: str) -> bool:
    lowered = text.lower()
    return not any(b.lower() in lowered for b in BLOCKLIST)


INSTRUCT_PAIRS = [
    ("What is 12 + 7?", "19."),
    ("Summarize: HERCULE verifies every tool result.",
     "HERCULE verifies tool results before trusting them."),
    ("Rewrite as a list: apples oranges pears.",
     "1. apples\n2. oranges\n3. pears"),
    ("Classify the request 'read the file' as QUESTION, GOAL, or MEMORY.",
     "GOAL"),
    ("Extract the number: order 451 crates.", "451"),
    ("Is the following plan complete? 1. List files. 2. Verify.",
     "Yes: it lists and verifies."),
    ("What is the capital of France?", "Paris."),
    ("Convert to JSON with keys name and count: 3 crates.",
     '{"name": "crates", "count": 3}'),
    ("Plan a file backup in two steps.",
     "1. Copy the files.\n2. Verify the copies."),
    ("Should HERCULE delete everything without approval?",
     "No: destructive actions need explicit approval."),
]


def build_instruct(rng: random.Random, count: int = 200) -> list:
    docs = []
    for i in range(count):
        q, a = INSTRUCT_PAIRS[i % len(INSTRUCT_PAIRS)]
        docs.append(f"INSTRUCTION:\n{q}\nRESPONSE:\n{a}\n")
    return docs


TOOL_TEMPLATES = [
    ("mathematics", '{"expression": "%d + %d"}', "Calculate %d + %d."),
    ("files", '{"operation": "read", "path": "notes-%d.txt"}',
     "Read the file notes-%d.txt."),
    ("research", '{"topic": "widget standard %d"}',
     "Research the widget standard %d."),
]


def build_tooluse(rng: random.Random, count: int = 60) -> list:
    docs = []
    for i in range(count):
        ability, args_tpl, desc_tpl = TOOL_TEMPLATES[i % len(TOOL_TEMPLATES)]
        n = rng.randint(10, 99)
        docs.append(
            f"TASK:\n{desc_tpl % ((n, n) if desc_tpl.count('%d') == 2 else (n,))}\n"
            f"TOOL_CALL:\n{ability} {args_tpl % ((n, n) if args_tpl.count('%d') == 2 else (n,))}\n"
            f"TOOL_RESULT:\n<provided by the tool layer at runtime>\n"
            f"FINAL_RESPONSE:\nDone.\n")
    return docs


CODE_SNIPPETS = [
    "def add(a, b):\n    return a + b\n",
    "def total(items):\n    total = 0\n    for x in items:\n        total += x\n    return total\n",
    "def is_even(n):\n    return n % 2 == 0\n",
    "def greet(name):\n    return 'Hello, ' + name\n",
    "def maximum(a, b):\n    if a > b:\n        return a\n    return b\n",
    "def count_down(n):\n    while n > 0:\n        n -= 1\n    return n\n",
    "def square_all(values):\n    return [v * v for v in values]\n",
    "def first(items):\n    if items:\n        return items[0]\n    return None\n",
]


def build_code(count: int = 64) -> list:
    docs = []
    for i in range(count):
        docs.append(f"SNIPPET:\n{CODE_SNIPPETS[i % len(CODE_SNIPPETS)]}")
    return docs


def main() -> int:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    files = {"instruct.txt": build_instruct(rng),
             "tooluse.txt": build_tooluse(rng),
             "code.txt": build_code()}
    for name, docs in files.items():
        text = "\n\n".join(docs) + "\n"
        assert _clean(text), f"blocklist hit in {name}"
        (OUT / name).write_text(text, encoding="utf-8")
    sources = [{"name": f"hercule-instruct-v1-{i}", "license": "HERCULE-authored (MIT, repo)",
                "origin": "hercule-authored", "url": "", "version": "v1", "files": [n]}
               for i, n in enumerate(files)]
    (OUT / "sources.json").write_text(json.dumps(sources, indent=1), encoding="utf-8")
    print(f"instruct files={len(files)} docs={sum(len(d) for d in files.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
