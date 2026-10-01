#!/usr/bin/env python
"""
Download datasets using HuggingFace datasets library directly.
"""
import os
import json
import subprocess
from pathlib import Path

def install_deps():
    """Install required packages."""
    subprocess.run(["pip", "install", "-q", "datasets", "pyarrow", "tqdm"], check=True)

def download_openwebtext_sample(max_chars: int = 20_000_000) -> int:
    """Download OpenWebText using datasets library."""
    try:
        from datasets import load_dataset
        
        print("Loading OpenWebText (1% sample)...")
        dataset = load_dataset("Skylion007/openwebtext", split="train[:1%]")
        
        output_file = Path("training/data/external/openwebtext_sample.jsonl")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        total = 0
        with open("training/data/external/openwebtext.jsonl", 'w', encoding='utf-8') as f:
            for item in dataset:
                text = item['text']
                if len(text) > 100:
                    f.write(json.dumps({"text": text, "source": "openwebtext"}) + '\n')
                    total += len(text)
                    if total >= 20_000_000:
                        break
        
        print(f"OpenWebText: {total:,} chars")
        return total
    except Exception as e:
        print(f"OpenWebText failed: {e}")
        return 0

def download_wikitext(max_chars: int = 20_000_000) -> int:
    """Download WikiText."""
    try:
        from datasets import load_dataset
        
        print("Loading WikiText-103...")
        dataset = load_dataset("Salesforce/wikitext", "wikitext-103-raw-v1", split="train")
        
        total = 0
        with open("training/data/external/wikitext.jsonl", 'w', encoding='utf-8') as f:
            for item in dataset:
                text = item['text']
                if len(text) > 100:
                    f.write(json.dumps({"text": text, "source": "wikitext"}) + '\n')
                    total += len(text)
                    if total >= 20_000_000:
                        break
        
        print(f"WikiText: {total:,} chars")
        return total
    except Exception as e:
        print(f"WikiText failed: {e}")
        return 0

def download_tinystories(max_chars: int = 10_000_000) -> int:
    try:
        from datasets import load_dataset
        
        print("Loading TinyStories...")
        dataset = load_dataset("roneneldan/TinyStories", split="train[:5%]")
        
        total = 0
        with open("training/data/external/tinystories.jsonl", 'w', encoding='utf-8') as f:
            for item in dataset:
                text = item['text']
                if len(text) > 100:
                    f.write(json.dumps({"text": text, "source": "tinystories"}) + '\n')
                    total += len(text)
                    if total >= max_chars:
                        break
        
        print(f"TinyStories: {total:,} chars")
        return total
    except Exception as e:
        print(f"TinyStories failed: {e}")
        return 0

def download_c4_sample(max_chars: int = 20_000_000) -> int:
    """Download a sample of C4 dataset."""
    try:
        from datasets import load_dataset
        
        print("Loading C4 (1% sample)...")
        dataset = load_dataset("allenai/c4", "en", split="train[:1%]")
        
        total = 0
        with open("training/data/external/c4_sample.jsonl", 'w', encoding='utf-8') as f:
            for item in dataset:
                text = item['text']
                if len(text) > 100:
                    f.write(json.dumps({"text": item['text'], "source": "c4"}) + '\n')
                    total += len(text)
                    if total >= max_chars:
                        break
        
        print(f"C4 sample: {total:,} chars")
        return total
    except Exception as e:
        print(f"C4 failed: {e}")
        return 0

def main():
    # Install deps
    import subprocess
    subprocess.run(["pip", "install", "-q", "datasets", "pyarrow", "tqdm"], check=True)
    
    # Create output dir
    from pathlib import Path
    output_dir = Path("training/data/external")
    Path("training/data/external").mkdir(parents=True, exist_ok=True)
    
    total_chars = 0
    
    print("=== Downloading datasets ===")
    
    # 1. TinyStories (high quality, small)
    total = download_tinystories(10_000_000)
    print(f"Total so far: {total:,} chars")
    
    # 2. TinyStories (larger sample)
    total += download_tinystories(10_000_000)
    print(f"Total so far: {total:,} chars")
    
    # 3. WikiText
    total += download_wikitext(20_000_000)
    print(f"Total so far: {total:,} chars")
    
    # 4. OpenWebText sample
    total += download_openwebtext_sample(20_000_000)
    print(f"Total so far: {total:,} chars")
    
    # 4. C4 sample
    total += download_c4_sample(20_000_000)
    print(f"Total so far: {total:,} chars")
    
    print(f"\nTotal external data: {total:,} chars")
    print(f"Need {100_000_000:,} chars for 100M tokens")
    
    # Merge with local corpus
    print("\nMerging with local corpus...")
    merge_corpora()

def merge_corpora():
    """Merge local and external corpora."""
    all_texts = []
    
    # Read local
    with open("training/data/large_corpus/corpus.jsonl", 'r') as f:
        for line in open("training/data/large_corpus/corpus.jsonl"):
            data = json.loads(line)
            yield data['text']
    
    # Read external
    for f in ["training/data/external/openwebtext.jsonl", 
              "training/data/external/wikitext.jsonl",
              "training/data/external/tinystories.jsonl",
              "training/data/external/c4_sample.jsonl"]:
        if os.path.exists(f):
            with open(f) as f:
                for line in f:
                    data = json.loads(line)
                    yield data['text']


if __name__ == "__main__":
    import os
    os.makedirs("training/data/external", exist_ok=True)
    main()