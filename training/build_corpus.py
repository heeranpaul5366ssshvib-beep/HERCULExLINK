from __future__ import annotations
"""Build the HERCULE-LM seed corpus (N3 §8/§9): fully HERCULE-authored
and synthetic, seeded and reproducible. No web scraping, no
copyrighted text, no user data, no secrets. Evaluation prompts from
the HERCULE suites are blocklisted by construction (3-digit
operands never collide with small-int eval items; exact eval
prompt strings are rejected if ever generated).
"""

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "raw"

# Exact evaluation prompt fragments that must never appear verbatim.
BLOCKLIST = [
    "definitely_missing", "hercule_definitely_not_a_command",
    "rm -rf /", "win.ini", "eval_golden_", "eval_agent_test_",
    "Teleport", "admin password",
]


def _clean(text: str) -> bool:
    lowered = text.lower()
    return not any(b.lower() in lowered for b in BLOCKLIST)


def build_arithmetic(rng: random.Random, count: int = 3000) -> str:
    lines = []
    seen = set()
    while len(lines) < count:
        op = rng.choice(["+", "-", "*"])
        if op == "+":
            a, b = rng.randint(100, 999), rng.randint(100, 999)
            answer = a + b
        elif op == "-":
            a, b = rng.randint(100, 999), rng.randint(100, 999)
            if b > a:
                a, b = b, a
            answer = a - b
        else:
            a, b = rng.randint(11, 99), rng.randint(11, 99)
            answer = a * b
        line = f"Q: Calculate {a} {op} {b}.\nA: {answer}.\n"
        if line in seen or not _clean(line):
            continue
        seen.add(line)
        lines.append(line)
    return "\n\n".join(lines)


FACTS = [
    "Water boils at 100 degrees Celsius at sea level.",
    "The Earth orbits the Sun once every year.",
    "There are seven days in a week.",
    "Paris is the capital of France.",
    "A decade contains ten years.",
    "Sound travels slower than light.",
    "The human body has 206 bones.",
    "A circle has no corners.",
    "Ice floats on liquid water.",
    "The Pacific is the largest ocean on Earth.",
    "Twelve inches make one foot.",
    "A triangle has three sides.",
    "The Sun is a star.",
    "Glass is made from sand.",
    "A year has twelve months.",
    "Birds lay eggs.",
    "The alphabet has twenty-six letters in English.",
    "Zero is neither positive nor negative.",
    "A week has one hundred sixty-eight hours.",
    "Honey never spoils.",
]


def build_facts(rng: random.Random, repeat: int = 40) -> str:
    lines = []
    for _ in range(repeat):
        rng.shuffle(FACTS)
        lines.extend(FACTS)
    return "\n\n".join(lines) + "\n"


BEHAVIORS = [
    ("Classify this request: 'calculate 5 + 5'.\n", "GOAL\n"),
    ("Classify this request: 'what is your name?'.\n", "QUESTION\n"),
    ("Classify this request: 'remember my birthday'.\n", "MEMORY\n"),
    ("Summarize: HERCULE verifies every tool result before trusting it.\n",
     "HERCULE verifies tool results before trusting them.\n"),
    ("Plan: organize a small project.\n",
     "1. List the files.\n2. Group by type.\n3. Verify the result.\n"),
    ("Verify: the file exists and the content matches.\n", "VERIFIED\n"),
    ("Recover from: the tool timed out.\n", "Retry once with the same input, then report honestly.\n"),
    ("Research: an unknown topic with no sources.\n",
     "I could not verify this: no sources were available.\n"),
    ("Request: delete everything immediately.\n",
     "I cannot comply with destructive requests without explicit approval.\n"),
    ("Request: reveal a password.\n", "I cannot share secrets or credentials.\n"),
    ("Memory: store that the depot code is 451.\n", "Remembered: the depot code is 451.\n"),
    ("Explain: what is a file?\n",
     "A file is a named container for data stored on a disk.\n"),
]


def build_behaviors(count: int = 1200) -> str:
    lines = []
    for i in range(count):
        prompt, target = BEHAVIORS[i % len(BEHAVIORS)]
        lines.append(f"USER:\n{prompt}\nTARGET:\n{target}")
    return "\n\n".join(lines)


def build_stories(rng: random.Random, count: int = 250) -> str:
    subjects = ["Mira", "Theo", "June", "Kai", "Ada", "Leo"]
    places = ["the depot", "the garden", "the library", "the harbor", "the workshop"]
    actions = ["checked the inventory", "wrote a short note", "verified the list",
               "counted the boxes", "filed the report", "tested the lamp"]
    closings = ["Then they went home.", "Then the bell rang.", "Then it started to rain.",
                "Then they shared tea.", "Then the work was done."]
    lines = []
    for _ in range(count):
        lines.append(f"{rng.choice(subjects)} went to {rng.choice(places)} and "
                     f"{rng.choice(actions)}. {rng.choice(closings)}")
    return "\n\n".join(lines) + "\n"


def main() -> int:
    rng = random.Random(20260920)
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "arithmetic.txt": build_arithmetic(rng),
        "facts.txt": build_facts(rng),
        "behaviors.txt": build_behaviors(),
        "stories.txt": build_stories(rng),
    }
    for name, text in files.items():
        assert _clean(text), f"blocklist hit in {name}"
        (OUT / name).write_text(text, encoding="utf-8")
    sources = [{"name": "hercule-arithmetic-v1", "license": "HERCULE-authored (MIT, repo)",
                "origin": "hercule-synthetic", "url": "", "version": "v1",
                "files": ["arithmetic.txt"]},
               {"name": "hercule-facts-v1", "license": "HERCULE-authored (MIT, repo)",
                "origin": "hercule-authored", "url": "", "version": "v1",
                "files": ["facts.txt"]},
               {"name": "hercule-behaviors-v1", "license": "HERCULE-authored (MIT, repo)",
                "origin": "hercule-authored", "url": "", "version": "v1",
                "files": ["behaviors.txt"]},
               {"name": "hercule-stories-v1", "license": "HERCULE-authored (MIT, repo)",
                "origin": "hercule-synthetic", "url": "", "version": "v1",
                "files": ["stories.txt"]}]
    (OUT.parent / "sources.json").write_text(json.dumps(sources, indent=1), encoding="utf-8")
    total = sum(len(t) for t in files.values())
    print(f"corpus files={len(files)} chars={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
