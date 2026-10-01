from __future__ import annotations
"""N8 corpus builders (N8.4/N8.8-N8.10): deterministic, MIT-authored.

- B (seed_unique): seed corpus deduplicated to unique paragraphs.
- C (expanded): seed-unique + newly authored material (~2x tokens).
- D (controlled_2x): seed-unique, each document exactly twice.
- E (arithmetic): arithmetic pairs + 10% mixed sample (seeded).

Every corpus gets sources.json + manifest (counts, hashes). The N7
eval set and arithmetic eval pairs are checked against every corpus
(exact + normalized); a violation aborts the build.
"""

import hashlib
import json
import random
from pathlib import Path

N8 = Path(__file__).resolve().parent
RAW = N8.parent / "data" / "raw"
CORPORA = N8 / "corpora"
SEED = 88031

EXTRA_FACTS = [
    "Copper conducts electricity well.",
    "The Nile is one of the longest rivers in the world.",
    "A century contains one hundred years.",
    "The Moon orbits the Earth.",
    "Iron rusts in the presence of water and air.",
    "A hexagon has six sides.",
    "The speed of light is faster than the speed of sound.",
    "Ants live in colonies.",
    "The capital of Japan is Tokyo.",
    "A kilogram contains one thousand grams.",
    "Sharks have no bones, only cartilage.",
    "The Great Wall is in China.",
    "A leap year has three hundred sixty-six days.",
    "Venus is the hottest planet in the solar system.",
    "Bees make honey in hives.",
    "The human heart has four chambers.",
    "A pentagon has five sides.",
    "Silver conducts electricity better than copper.",
    "The Amazon is a vast rainforest.",
    "A millisecond is one thousandth of a second.",
    "Owls can turn their heads very far.",
    "The capital of Italy is Rome.",
    "A liter contains one thousand milliliters.",
    "Penguins cannot fly but swim well.",
    "The Sahara is a large desert.",
    "A dozen means twelve.",
    "Spiders have eight legs.",
    "The capital of Spain is Madrid.",
    "A byte contains eight bits.",
    "Dolphins sleep with one eye open.",
    "The Eiffel Tower is in Paris.",
    "A gross means one hundred forty-four.",
    "Cacti store water in their stems.",
    "The capital of Canada is Ottawa.",
    "A score means twenty.",
    "Bats navigate using sound.",
    "Mount Everest is Earth's highest mountain.",
    "A fortnight is fourteen nights.",
    "Octopuses have three hearts.",
    "The capital of Brazil is Brasilia.",
]

DEFINITIONS = [
    ("Verify", "to check that something is true or correct"),
    ("Plan", "a list of steps to reach a goal"),
    ("Memory", "stored information that can be recalled later"),
    ("Policy", "a rule that decides what is allowed"),
    ("Tool", "an instrument used to perform a task"),
    ("Skill", "a validated reusable procedure"),
    ("Evidence", "observed facts that support a claim"),
    ("Risk", "the chance of an unwanted outcome"),
    ("Goal", "a desired future state"),
    ("Task", "a unit of work with a clear end"),
    ("Agent", "a system that acts toward goals"),
    ("Model", "a mathematical description learned from data"),
    ("Token", "a piece of text used by a language model"),
    ("Epoch", "one full pass over training data"),
    ("Batch", "a group of examples processed together"),
]


def _paras(files):
    docs = []
    for name in files:
        text = (RAW / name).read_text(encoding="utf-8")
        docs.extend([c.strip() + "\n" for c in text.split("\n\n") if c.strip()])
    return docs


def _arith_pairs(files):
    import re

    pairs = set()
    for name in files:
        for m in re.finditer(r"Calculate (\d+) (.) (\d+)", (RAW / name).read_text(encoding="utf-8")):
            pairs.add((m.group(1), m.group(2), m.group(3)))
    return pairs


def _write_corpus(corpus_id, files_dict, license="HERCULE-authored (MIT, repo)"):
    root = CORPORA / corpus_id
    root.mkdir(parents=True, exist_ok=True)
    file_list = []
    for name, docs in files_dict.items():
        (root / name).write_text("\n\n".join(docs) + "\n", encoding="utf-8")
        file_list.append(name)
    sources = [{"name": f"{corpus_id}-{i}", "license": license,
                "origin": "hercule-synthetic" if "arith" in n else "hercule-authored",
                "url": "", "version": "v1", "files": [n]}
               for i, n in enumerate(file_list)]
    (root / "sources.json").write_text(json.dumps(sources, indent=1), encoding="utf-8")
    return root


def _manifest(corpus_id):
    from models.hercule_lm.data import (DataSource, check_no_leakage, dataset_manifest,
                                        load_documents, split_documents,
                                        validate_documents)

    root = CORPORA / corpus_id
    sources = [DataSource(**s) for s in json.loads((root / "sources.json").read_text(encoding="utf-8"))]
    docs = load_documents(str(root), sources, paragraphs=True)
    validate_documents(docs, ["HERCULE-authored (MIT, repo)"])
    splits = split_documents(docs)
    leak = check_no_leakage(splits)
    assert not leak["overlap"], leak["overlap"]
    manifest = dataset_manifest(corpus_id, "v1", sources, docs, splits)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest, docs


def _contamination_check(name, docs):
    from training.n7.build_eval_set import _items as eval_items  # noqa (deterministic set)

    eval_prompts = [i["prompt"] for i in eval_items()]
    texts = [d.text for d in docs]
    norm = lambda s: " ".join(str(s or "").split()).lower()  # noqa: E731
    normed = {norm(t) for t in texts}
    hits = [p for p in eval_prompts if p in texts or norm(p) in normed]
    assert not hits, f"{name} contaminated: {hits[:3]}"
    return True


def main() -> int:
    rng = random.Random(SEED)
    seed_files = ["arithmetic.txt", "facts.txt", "behaviors.txt", "stories.txt",
                  "tool_calls.txt", "permission_aware.txt", "fail_correct.txt", "multi_pass_reasoning.txt"]
    seed_docs = _paras(seed_files)
    seen, unique = set(), []
    for doc in seed_docs:
        if doc not in seen:
            seen.add(doc)
            unique.append(doc)
    print(f"seed docs={len(seed_docs)} unique={len(unique)} "
          f"repetition_ratio={len(seed_docs) / max(1, len(unique)):.2f}")

    # B: deduped seed.
    _write_corpus("seed_unique", {"seed_unique.txt": unique})
    # D: controlled 2x (deduped, each exactly twice).
    _write_corpus("controlled_2x", {"controlled_2x.txt": unique * 2})
    # C: expanded = unique seed + new authored material.
    seed_pairs = _arith_pairs(seed_files)
    new_arith = []
    while len(new_arith) < 3000:
        op = rng.choice(["+", "-", "*"])
        if op == "+":
            a, b = rng.randint(100, 999), rng.randint(100, 999)
        elif op == "-":
            a, b = rng.randint(100, 999), rng.randint(100, 999)
            a, b = (b, a) if b > a else (a, b)
        else:
            a, b = rng.randint(101, 199), rng.randint(101, 199)
        key = (str(a), op, str(b))
        if key in seed_pairs:
            continue
        seed_pairs.add(key)
        answer = a + b if op == "+" else (a - b if op == "-" else a * b)
        new_arith.append(f"Q: Calculate {a} {op} {b}.\nA: {answer}.\n")
    rng.shuffle(EXTRA_FACTS)
    new_facts = list(EXTRA_FACTS)
    new_defs = [f"{term} means {definition}.\n" for term, definition in DEFINITIONS]
    subjects = ["Noor", "Felix", "Ivy", "Omar", "Lena", "Ravi"]
    places = ["the archive", "the observatory", "the market", "the station", "the orchard"]
    actions = ["mapped the shelves", "logged the readings", "counted the crates",
               "swept the platform", "picked the fruit"]
    closings = ["Then the shift ended.", "Then the lights dimmed.", "Then a bell rang.",
                "Then they wrote it down.", "Then the day was done."]
    new_stories = [f"{rng.choice(subjects)} visited {rng.choice(places)} and "
                   f"{rng.choice(actions)}. {rng.choice(closings)}\n" for _ in range(300)]
    _write_corpus("expanded", {
        "seed_unique.txt": unique,
        "new_arithmetic.txt": new_arith,
        "new_facts.txt": new_facts,
        "new_definitions.txt": new_defs,
        "new_stories.txt": new_stories})
    # E: arithmetic pairs (seed+new, deduped) + 10% mixed sample.
    arith_docs = [d for d in unique if d.startswith("Q: Calculate")] + new_arith
    mixed = rng.sample(unique, max(1, len(unique) // 10))
    _write_corpus("arithmetic", {"arithmetic.txt": arith_docs, "mixed.txt": mixed})

    for corpus_id in ("seed_unique", "controlled_2x", "expanded", "arithmetic"):
        manifest, docs = _manifest(corpus_id)
        _contamination_check(corpus_id, docs)
        print(f"{corpus_id}: docs={manifest['documents']} "
              f"hash={manifest['dataset_hash']} splits="
              f"{ {k: v['documents'] for k, v in manifest['splits'].items()} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
