#!/usr/bin/env python
"""
Build large-scale training corpus (100M+ tokens) from diverse sources.
"""
import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Generator
import requests
from tqdm import tqdm

class CorpusBuilder:
    def __init__(self, target_tokens: int = 100_000_000, output_dir: str = "training/data/large_corpus"):
        self.target_tokens = target_tokens
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.total_chars = 0
        self.sources = []
        
    def add_local_sources(self) -> List[str]:
        """Add all local text files."""
        texts = []
        for root, _, files in os.walk("training/data"):
            for f in files:
                if f.endswith(('.txt', '.json', '.md', '.py', '.jsonl')):
                    path = Path(root) / f
                    try:
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            text = f.read()
                            if len(text) > 100:
                                texts.append(text)
                    except:
                        pass
        return texts
    
    def add_curriculum_data(self) -> List[str]:
        """Add curriculum data."""
        texts = []
        for root, _, files in os.walk("training/curriculum_cache"):
            for f in files:
                if f.endswith(('.json', '.npy')):
                    path = Path(root) / f
                    try:
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            text = f.read()[:50000]
                            if len(text) > 100:
                                texts.append(text)
                    except:
                        pass
        return texts
    
    def add_github_code(self) -> List[str]:
        """Add code from local repos."""
        texts = []
        for root, _, files in os.walk("."):
            for f in files:
                if f.endswith(('.py', '.js', '.ts', '.cpp', '.c', '.h', '.rs', '.go', '.java', '.md', '.txt')):
                    if any(skip in root for skip in ['.git', '__pycache__', '.venv', 'venv', 'node_modules', '.tmp', 'artifacts']):
                        continue
                    path = Path(root) / f
                    try:
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            text = f.read()
                            if len(text) > 500:
                                texts.append(text)
                    except:
                        pass
        return texts
    
    def fetch_openwebtext(self, max_chars: int = 50_000_000) -> List[str]:
        """Fetch from OpenWebText (placeholder - implement actual download)."""
        # TODO: Implement actual download from OpenWebText dump
        # For now, return empty
        return []
    
    def fetch_wikipedia(self, max_chars: int = 30_000_000) -> List[str]:
        """Fetch Wikipedia dump (placeholder)."""
        # TODO: Implement Wikipedia dump download
        return []
    
    def fetch_github_code(self, max_chars: int = 20_000_000) -> List[str]:
        """Fetch GitHub code (placeholder)."""
        # TODO: Implement GitHub code download
        return []
    
    def build(self) -> Dict:
        """Build the full corpus."""
        print("Building large corpus...")
        all_texts = []
        
        # Local sources (high quality, curated)
        local_texts = self.add_local_sources()
        print(f"Local sources: {len(local_texts)} docs, {sum(len(t) for t in local_texts):,} chars")
        all_texts.extend(local_texts)
        
        # Curriculum data
        curr_texts = self.add_curriculum_data()
        print(f"Curriculum: {len(curr_texts)} docs, {sum(len(t) for t in curr_texts):,} chars")
        all_texts.extend(curr_texts)
        
        # Local code
        code_texts = self.add_github_code()
        print(f"Local code: {len(code_texts)} files, {sum(len(t) for t in code_texts):,} chars")
        all_texts.extend(code_texts)
        
        # TODO: Add external sources (OpenWebText, Wikipedia, GitHub, etc.)
        # web_texts = self.fetch_openwebtext()
        # wiki_texts = self.fetch_wikipedia()
        # gh_texts = self.fetch_github_code()
        # all_texts.extend(web_texts + wiki_texts + gh_texts)
        
        # Save combined corpus
        output_file = self.output_dir / "corpus.jsonl"
        total_chars = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            for text in all_texts:
                if len(text) > 100:
                    f.write(json.dumps({"text": text, "source": "local"}) + '\n')
                    total_chars += len(text)
        
        print(f"\nTotal: {total_chars:,} chars ({total_chars/4:,} estimated tokens)")
        return {
            "total_chars": total_chars,
            "num_docs": len(all_texts),
            "output_file": str(output_file)
        }


def main():
    builder = CorpusBuilder(target_tokens=100_000_000, output_dir="training/data/large_corpus")
    result = builder.build()
    print(f"\nCorpus built: {result}")


if __name__ == "__main__":
    main()