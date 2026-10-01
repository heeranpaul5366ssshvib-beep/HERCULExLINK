#!/usr/bin/env python
"""
Fetch external data sources for large corpus.
Downloads from public datasets: OpenWebText, Wikipedia, GitHub, etc.
"""
import os
import json
import hashlib
import requests
from pathlib import Path
from tqdm import tqdm
import gzip
import tarfile

class ExternalDataFetcher:
    def __init__(self, output_dir: str = "training/data/external", target_chars: int = 100_000_000):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.target_chars = target_chars
        self.total_chars = 0
        
    def download_openwebtext(self, max_chars: int = 30_000_000) -> int:
        """Download OpenWebText subset."""
        url = "https://huggingface.co/datasets/Skylion007/openwebtext/resolve/main/data/train-00000-of-00001.parquet"
        # For now, use a smaller approach - download a text dump
        # This is a placeholder - in reality you'd stream the parquet
        print("OpenWebText download not implemented yet - use local mirror")
        return 0
    
    def download_wikipedia(self, max_chars: int = 30_000_000) -> int:
        """Download Wikipedia dump."""
        # Use wikidata dumps or Wikipedia API
        print("Wikipedia download not implemented yet")
        return 0
    
    def download_github_code(self, max_chars: int = 20_000_000) -> int:
        """Download GitHub code from CodeParrot or similar."""
        print("GitHub code download not implemented yet")
        return 0
    
    def download_the_pile(self, max_chars: int = 20_000_000) -> int:
        """Download The Pile dataset components."""
        print("The Pile download not implemented yet")
        return 0
    
    def fetch_c4(self, max_chars: int = 20_000_000) -> int:
        """Fetch C4 dataset (Common Crawl)."""
        print("C4 dataset download not implemented yet")
        return 0

def download_openwebtext_subset():
    """Download a subset of OpenWebText from a mirror."""
    urls = [
        "https://huggingface.co/datasets/Skylion007/openwebtext/resolve/main/data/train-00000-of-00001.parquet",
    ]
    # This would need actual implementation
    pass

def create_synthetic_diverse_data(target_chars: int = 50_000_000) -> int:
    """Create diverse synthetic data for training."""
    import random
    import string
    
    templates = [
        # Code templates
        ("python", """
def {func_name}({param}):
    \"\"\"{docstring}\"\"\"
    {body}
    return {result}
"""),
        ("javascript", """
function {func_name}({param}) {{
    // {docstring}
    {body}
    return {result};
}}
"""),
        # Explanation templates
        ("explanation", """
Question: {question}
Answer: {answer}
Explanation: {explanation}
"""),
        # Reasoning templates
        ("reasoning", """
Problem: {problem}
Step 1: {step1}
Step 2: {step2}
Step 3: {step3}
Conclusion: {conclusion}
"""),
    ]
    
    topics = [
        "sorting algorithms", "dynamic programming", "graph algorithms",
        "machine learning", "neural networks", "optimization",
        "data structures", "algorithms", "complexity analysis",
        "probability", "statistics", "linear algebra", "calculus",
        "physics", "chemistry", "biology", "engineering",
    ]
    
    # This is a placeholder - in reality you'd generate more diverse content
    return 0

def fetch_from_huggingface():
    """Fetch datasets from HuggingFace Hub."""
    try:
        from datasets import load_dataset
        
        # Load OpenWebText subset
        dataset = load_dataset("Skylion007/openwebtext", split="train[:1%]")
        texts = [item['text'] for item in dataset]
        
        output_file = Path("training/data/external/openwebtext_sample.jsonl")
        with open(output_file, 'w', encoding='utf-8') as f:
            for text in texts:
                if len(text) > 100:
                    f.write(json.dumps({"text": text, "source": "openwebtext"}) + '\n')
        
        print(f"Saved {len(texts)} documents from OpenWebText")
        return len(texts)
    except Exception as e:
        print(f"Failed to fetch from HF: {e}")
        return 0


def main():
    output_dir = Path("training/data/external")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    total_chars = 0
    
    # 1. Try to fetch from HuggingFace
    print("Fetching from HuggingFace...")
    chars = fetch_from_huggingface()
    # This will fail if no internet/datasets library
    
    # For now, create a larger corpus from what we have
    # by augmenting existing data
    print("Augmenting existing corpus...")
    
    # Read existing corpus
    with open("training/data/large_corpus/corpus.jsonl", 'r') as f:
        lines = f.readlines()
    
    # Augment by creating variations
    augmented = []
    for line in lines[:1000]:  # First 1000
        data = json.loads(line)
        text = data['text']
        augmented.append(data)
        # Add variations
        if len(text) > 500:
            # Split into chunks
            chunks = [text[i:i+1000] for i in range(0, len(text), 800)]
            for chunk in chunks:
                if len(chunk) > 100:
                    augmented.append({"text": chunk, "source": "augmented"})
    
    # Save augmented corpus
    augmented_file = Path("training/data/large_corpus/corpus_augmented.jsonl")
    with open(augmented_file, 'w') as f:
        for item in augmented:
            f.write(json.dumps(item) + '\n')
    
    print(f"Created augmented corpus with {len(augmented)} entries")


if __name__ == "__main__":
    main()