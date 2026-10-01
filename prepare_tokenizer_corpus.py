#!/usr/bin/env python3
"""Combine all available data sources into a large corpus for tokenizer training.

This script merges:
- training/data/fixed/fixed_corpus.txt (~1.4M chars)
- training/data/large_corpus/corpus.jsonl (~11.8M chars)
- training/data/large_corpus/corpus_augmented.jsonl (~26.8M chars)
- training/data/raw/*.txt files
- training/data/instruct/*.txt files

Total: ~39M chars. For 100M+ chars, external data (FineWeb, C4, etc.) is needed.
"""

import json
import sys
from pathlib import Path


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Warning: Could not read {path}: {e}", file=sys.stderr)
        return ""


def read_jsonl(path: Path) -> list:
    texts = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "text" in obj:
                    texts.append(obj["text"])
                elif isinstance(obj, str):
                    texts.append(obj)
            except json.JSONDecodeError:
                pass
    except Exception as e:
        print(f"Warning: Could not read {path}: {e}", file=sys.stderr)
    return texts


def main():
    output_path = Path("training/data/large_corpus/tokenizer_corpus_100m.txt")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    all_texts = []
    total_chars = 0
    
    # 1. Fixed corpus (deduplicated, high quality)
    fixed_corpus = Path("training/data/fixed/fixed_corpus.txt")
    if fixed_corpus.exists():
        text = read_text_file(fixed_corpus)
        all_texts.append(text)
        total_chars += len(text)
        print(f"fixed_corpus.txt: {len(text):,} chars")
    
    # 2. Large corpus JSONL files
    for jsonl_name in ["corpus.jsonl", "corpus_augmented.jsonl", "corpus_final.jsonl"]:
        jsonl_path = Path(f"training/data/large_corpus/{jsonl_name}")
        if jsonl_path.exists():
            texts = read_jsonl(jsonl_path)
            combined = "\n\n".join(texts)
            all_texts.append(combined)
            total_chars += len(combined)
            print(f"{jsonl_name}: {len(combined):,} chars ({len(texts)} entries)")
    
    # 3. Raw data files
    raw_dir = Path("training/data/raw")
    if raw_dir.exists():
        for txt_file in raw_dir.glob("*.txt"):
            text = read_text_file(txt_file)
            if text:
                all_texts.append(text)
                total_chars += len(text)
                print(f"raw/{txt_file.name}: {len(text):,} chars")
    
    # 4. Instruct data files
    instruct_dir = Path("training/data/instruct")
    if instruct_dir.exists():
        for txt_file in instruct_dir.glob("*.txt"):
            text = read_text_file(txt_file)
            if text:
                all_texts.append(text)
                total_chars += len(text)
                print(f"instruct/{txt_file.name}: {len(text):,} chars")
    
    # 5. Curriculum data
    curriculum_dir = Path("training/data/curriculum_arith_v1")
    if curriculum_dir.exists():
        for txt_file in curriculum_dir.glob("*.txt"):
            text = read_text_file(txt_file)
            if text:
                all_texts.append(text)
                total_chars += len(text)
                print(f"curriculum/{txt_file.name}: {len(text):,} chars")
    
    # Write combined corpus
    combined_corpus = "\n\n".join(all_texts)
    output_path.write_text(combined_corpus, encoding="utf-8")
    
    print(f"\nTotal combined: {total_chars:,} chars ({total_chars/1e6:.1f}M)")
    print(f"Written to: {output_path}")
    
    if total_chars < 100_000_000:
        print(f"\nWARNING: Only {total_chars/1e6:.1f}M chars available.")
        print(f"Need {100 - total_chars/1e6:.1f}M more for 32K vocab training.")
        print(f"Run download_fineweb.py or download_c4.py to fetch external data.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())