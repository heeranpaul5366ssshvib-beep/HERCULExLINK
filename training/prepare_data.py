from __future__ import annotations
"""Shim: validate corpus + print manifest (N3 §16).

Usage::

    python -m training.prepare_data [--corpus-dir training/data/raw]
"""

import argparse
import json
import sys
from pathlib import Path

from models.hercule_lm.data import (check_no_leakage, dataset_manifest,
                                    load_documents, split_documents,
                                    validate_documents, DataSource)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hercule-prepare-data")
    parser.add_argument("--corpus-dir", default="training/data/raw")
    parser.add_argument("--sources", default="training/data/sources.json")
    args = parser.parse_args(argv)
    try:
        sources = [DataSource(**s) for s in
                   json.loads(Path(args.sources).read_text(encoding="utf-8"))]
        docs = load_documents(args.corpus_dir, sources, paragraphs=True)
        validate_documents(docs, ["HERCULE-authored (MIT, repo)"])
    except ValueError as exc:
        print(f"INVALID_DATASET: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"NO_DATASET: {exc}", file=sys.stderr)
        return 2
    splits = split_documents(docs)
    leak = check_no_leakage(splits)
    if leak["overlap"]:
        print(f"DATASET LEAKAGE: {leak['overlap'][:3]}", file=sys.stderr)
        return 2
    manifest = dataset_manifest("hercule-seed", "v1", sources, docs, splits)
    print(json.dumps(manifest, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
