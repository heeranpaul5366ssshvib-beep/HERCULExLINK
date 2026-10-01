#!/usr/bin/env python
"""
Download actual datasets from public sources.
"""
import os
import json
import requests
from pathlib import Path
from tqdm import tqdm

# Datasets to download with their URLs
DATASETS = {
    "openwebtext_sample": {
        "url": "https://huggingface.co/datasets/Skylion007/openwebtext/resolve/main/data/train-00000-of-00001.parquet",
        "format": "parquet",
        "target_chars": 30_000_000
    },
    "wikitext": {
        "url": "https://huggingface.co/datasets/Salesforce/wikitext/resolve/main/wikitext-103-raw-v1/train-00000-of-00001.parquet",
        "format": "parquet",
        "target_chars": 30_000_000
    },
    "c4_en": {
        "url": "https://huggingface.co/datasets/allenai/c4/resolve/main/en/c4-train.00000-of-01024.json.gz",
        "format": "json.gz",
        "target_chars": 30_000_000
    },
    "codeparrot": {
        "url": "https://huggingface.co/datasets/transformersbook/codeparrot/resolve/main/train-00000-of-00001.parquet",
        "format": "parquet",
        "target_chars": 20_000_000
    },
    "the_pile": {
        "url": "https://huggingface.co/datasets/EleutherAI/the_pile_deduped/resolve/main/data/train/00.jsonl.zst",
        "format": "jsonl.zst",
        "target_chars": 20_000_000
    }
}

def download_file(url: str, dest: Path, chunk_size: int = 8192) -> bool:
    """Download a file with progress bar."""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total = int(response.headers.get('content-length', 0))
        
        with open(dest, 'wb') as f, tqdm(
            total=total, unit='B', unit_scale=True, desc=dest.name
        ) as pbar:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False

def extract_parquet(filepath: Path, output_file: Path, max_chars: int):
    """Extract text from parquet file."""
    try:
        import pyarrow.parquet as pq
        table = pq.read_table(filepath)
        texts = []
        for batch in table.to_batches():
            for col in batch.columns:
                if col.type == 'string':
                    texts.extend(col.to_pylist())
                    break
        
        total = 0
        with open(filepath.with_suffix('.jsonl'), 'w', encoding='utf-8') as f:
            for text in table.column(0).to_pylist():
                if len(text) > 100:
                    f.write(json.dumps({"text": text, "source": "dataset"}) + '\n')
                    if total >= max_chars:
                        break
        return total
    except Exception as e:
        print(f"Failed to extract parquet: {e}")
        return 0

def download_tinystories(max_chars: int = 10_000_000):
    """Download TinyStories dataset - smaller, good for testing."""
    url = "https://huggingface.co/datasets/roneneldan/TinyStories/resolve/main/data/train-00000-of-00001.parquet"
    dest = Path("training/data/external/tinystories.parquet")
    
    if download_file(url, dest):
        # Extract
        try:
            import pyarrow.parquet as pq
            table = pq.read_table("training/data/external/tinystories.parquet")
            total = 0
            with open("training/data/external/tinystories.jsonl", 'w', encoding='utf-8') as f:
                for text in table['text'].to_pylist():
                    if len(text) > 100:
                        f.write(json.dumps({"text": text, "source": "tinystories"}) + '\n')
                        total += len(text)
                        if total >= max_chars:
                            break
            return total
        except Exception as e:
            print(f"Failed to extract TinyStories: {e}")
    return 0

def download_wikitext(max_chars: int = 10_000_000):
    """Download WikiText-103."""
    url = "https://huggingface.co/datasets/Salesforce/wikitext/resolve/main/wikitext-103-raw-v1/train-00000-of-00001.parquet"
    dest = Path("training/data/external/wikitext.parquet")
    
    if download_file(url, dest):
        try:
            import pyarrow.parquet as pq
            table = pq.read_table("training/data/external/wikitext.parquet")
            total = 0
            with open("training/data/external/wikitext.jsonl", 'w', encoding='utf-8') as f:
                for text in table['text'].to_pylist():
                    if len(text) > 100:
                        f.write(json.dumps({"text": text, "source": "wikitext"}) + '\n')
                        total += len(text)
                        if total >= max_chars:
                            break
            return total
        except Exception as e:
            print(f"Failed to extract WikiText: {e}")
    return 0

def main():
    print("Downloading datasets for large corpus...")
    
    # Install required packages
    import subprocess
    subprocess.run(["pip", "install", "-q", "pyarrow", "zstandard", "tqdm", "requests"])
    
    total_chars = 0
    max_total = 100_000_000
    
    # 1. TinyStories (small, high quality)
    print("\n1. Downloading TinyStories...")
    total = download_tinystories(10_000_000)
    print(f"  Got {total:,} chars")
    
    # 2. WikiText
    print("\n2. Downloading WikiText...")
    total = download_wikitext(10_000_000)
    print(f"  Got {total:,} chars")
    
    print("\nFor more data, run the full dataset downloads:")
    print("  - OpenWebText: ~30M chars")
    print("  - WikiText-103: ~30M chars")
    print("  - C4: ~30M chars")
    print("  - CodeParrot: ~20M chars")
    print("  - The Pile: ~20M chars")
    print(f"\nTotal so far: ~10M chars (need {100_000_000:,} for 100M tokens)")


if __name__ == "__main__":
    main()