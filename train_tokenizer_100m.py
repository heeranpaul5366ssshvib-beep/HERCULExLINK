#!/usr/bin/env python3
"""Train 32K+ vocab BPE tokenizer for HERCULE-100M model.

Usage:
    python train_tokenizer_100m.py --corpus training/data/large_corpus/tokenizer_corpus_100m.txt --vocab-size 32768
    python train_tokenizer_100m.py --corpus training/data/large_corpus/fineweb_100m.txt --vocab-size 32768
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from models.hercule_lm.tokenizer import HerculeBPETokenizer, ALL_SPECIALS


def load_corpus(corpus_path: str) -> list:
    """Load corpus from text file (one doc per paragraph or full file)."""
    path = Path(corpus_path)
    text = path.read_text(encoding="utf-8")
    # Split on double newline to get documents
    docs = [doc.strip() for doc in text.split("\n\n") if doc.strip()]
    print(f"Loaded {len(docs)} documents from {corpus_path}")
    print(f"Total characters: {len(text):,}")
    return docs


def train_tokenizer(corpus_path: str, vocab_size: int, output_dir: str, corpus_version: str = "hercule-100m-v1"):
    """Train BPE tokenizer on corpus."""
    print(f"Loading corpus from {corpus_path}...")
    texts = load_corpus(corpus_path)
    
    print(f"Training BPE tokenizer with vocab_size={vocab_size}...")
    tokenizer = HerculeBPETokenizer.train(
        texts=texts,
        vocab_size=vocab_size,
        corpus_version=corpus_version,
        specials=ALL_SPECIALS
    )
    
    print(f"Tokenizer trained: vocab_size={tokenizer.vocab_size}, merges={len(tokenizer.merges)}")
    print(f"Checksum: {tokenizer.checksum()}")
    
    # Save tokenizer
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(output_path))
    
    # Save manifest
    manifest = tokenizer.manifest()
    manifest_path = output_path / "tokenizer.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    
    print(f"Saved tokenizer to {output_dir}")
    return tokenizer


def main():
    parser = argparse.ArgumentParser(description="Train 32K+ vocab tokenizer for HERCULE-100M")
    parser.add_argument("--corpus", default="training/data/large_corpus/tokenizer_corpus_100m.txt",
                        help="Path to corpus text file")
    parser.add_argument("--vocab-size", type=int, default=32768, help="Target vocabulary size")
    parser.add_argument("--output-dir", default="training/tokenizer/hercule-bpe-100m-v2",
                        help="Output directory for tokenizer")
    parser.add_argument("--corpus-version", default="hercule-100m-v2", help="Corpus version string")
    args = parser.parse_args()
    
    tokenizer = train_tokenizer(
        corpus_path=args.corpus,
        vocab_size=args.vocab_size,
        output_dir=args.output_dir,
        corpus_version=args.corpus_version
    )
    
    # Test tokenizer
    test_text = "Hello, world! This is a test of the HERCULE 100M tokenizer."
    ids = tokenizer.encode(test_text)
    decoded = tokenizer.decode(ids)
    print(f"\nTest encode/decode:")
    print(f"  Input:    {test_text}")
    print(f"  Tokens:   {ids}")
    print(f"  Decoded:  {decoded}")
    print(f"  Match:    {test_text == decoded}")


if __name__ == "__main__":
    main()