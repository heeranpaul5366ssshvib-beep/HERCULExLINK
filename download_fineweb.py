#!/usr/bin/env python3
"""Download FineWeb-Edu (or similar) dataset for 100M+ chars tokenizer training.

Usage:
    python download_fineweb.py --target-chars 100000000 --output training/data/large_corpus/fineweb_100m.txt
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from datasets import load_dataset
except ImportError:
    print("Installing datasets...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "datasets", "huggingface_hub"])
    from datasets import load_dataset


def download_fineweb_edu(target_chars: int, output_path: str, seed: int = 42) -> int:
    """Download FineWeb-Edu dataset until target_chars reached."""
    print(f"Loading FineWeb-Edu (sample-10BT)...")
    ds = load_dataset("HuggingFaceFW/fineweb-edu", name="sample-10BT", split="train", streaming=True)
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
            
            f.write(text + "\n\n")
            total_chars += len(text)
            count += 1
            
            if count % 1000 == 0:
                print(f"  Downloaded {count} docs, {total_chars/1e6:.1f}M chars...")
            
            if total_chars >= target_chars:
                break
    
    print(f"Done: {count} documents, {total_chars:,} chars ({total_chars/1e6:.1f}M)")
    return total_chars


def download_redpajama(target_chars: int, output_path: str, seed: int = 42) -> int:
    """Download RedPajama dataset until target_chars reached."""
    print(f"Loading RedPajama...")
    ds = load_dataset("togethercomputer/RedPajama-Data-1T", split="train", streaming=True)
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
            
            f.write(text + "\n\n")
            total_chars += len(text)
            count += 1
            
            if count % 1000 == 0:
                print(f"  Downloaded {count} docs, {total_chars/1e6:.1f}M chars...")
            
            if total_chars >= target_chars:
                break
    
    print(f"Done: {count} documents, {total_chars:,} chars ({total_chars/1e6:.1f}M)")
    return total_chars


def main():
    parser = argparse.ArgumentParser(description="Download 100M+ chars for tokenizer training")
    parser.add_argument("--target-chars", type=int, default=100_000_000, help="Target characters (default: 100M)")
    parser.add_argument("--output", default="training/data/large_corpus/fineweb_100m.txt", help="Output file path")
    parser.add_argument("--source", choices=["fineweb", "redpajama"], default="fineweb", help="Data source")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()
    
    if args.source == "fineweb":
        download_fineweb_edu(args.target_chars, args.output, args.seed)
    else:
        download_redpajama(args.target_chars, args.output, args.seed)


if __name__ == "__main__":
    main()