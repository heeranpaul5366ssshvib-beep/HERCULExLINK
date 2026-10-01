#!/usr/bin/env python3
"""Download C4 dataset for tokenizer training (more reliable than FineWeb)."""

import argparse
import sys
from pathlib import Path

try:
    from datasets import load_dataset
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "datasets"])
    from datasets import load_dataset


def download_c4(target_chars: int, output_path: str, seed: int = 42) -> int:
    """Download C4 (Colossal Clean Crawled Corpus) en subset."""
    print(f"Loading C4 (en)...")
    ds = load_dataset("allenai/c4", "en", split="train", streaming=True)
    ds = ds.shuffle(seed=seed, buffer_size=10000)
    
    total_chars = 0
    count = 0
    
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for item in ds:
            text = item.get("text", "")
            if not text:
                continue
            
            # Clean up C4 text
            text = text.strip()
            if len(text) < 50:  # Skip very short documents
                continue
            
            f.write(text + "\n\n")
            total_chars += len(text)
            count += 1
            
            if count % 1000 == 0:
                print(f"  Downloaded {count} docs, {total_chars/1e6:.1f}M chars...")
            
            if total_chars >= target_chars:
                break
    
    print(f"Done: {count} documents, {total_chars:,} chars ({total_chars/1e6:.1f}M)")
    return total_chars


def download_wikitext(target_chars: int, output_path: str) -> int:
    """Download WikiText-103."""
    print(f"Loading WikiText-103...")
    ds = load_dataset("wikitext", "wikitext-103-raw-v1", split="train")
    
    total_chars = 0
    count = 0
    
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for item in ds:
            text = item.get("text", "")
            if not text or text.startswith("="):  # Skip headers
                continue
            text = text.strip()
            if len(text) < 50:
                continue
            
            f.write(text + "\n\n")
            total_chars += len(text)
            count += 1
            
            if total_chars >= target_chars:
                break
    
    print(f"Done: {count} documents, {total_chars:,} chars ({total_chars/1e6:.1f}M)")
    return total_chars


def main():
    parser = argparse.ArgumentParser(description="Download C4 or WikiText for tokenizer training")
    parser.add_argument("--target-chars", type=int, default=100_000_000, help="Target characters")
    parser.add_argument("--output", default="training/data/large_corpus/c4_100m.txt", help="Output file path")
    parser.add_argument("--source", choices=["c4", "wikitext"], default="c4", help="Data source")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()
    
    if args.source == "c4":
        download_c4(args.target_chars, args.output, args.seed)
    else:
        download_wikitext(args.target_chars, args.output)


if __name__ == "__main__":
    main()