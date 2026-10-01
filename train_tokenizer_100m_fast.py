#!/usr/bin/env python3
"""Train fast BPE tokenizer using HuggingFace tokenizers (Rust backend)."""

import argparse
import json
from pathlib import Path

try:
    from tokenizers import Tokenizer, models, trainers, pre_tokenizers, decoders, processors
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tokenizers"])
    from tokenizers import Tokenizer, models, trainers, pre_tokenizers, decoders, processors


def train_fast_tokenizer(corpus_path: str, vocab_size: int, output_dir: str):
    """Train BPE tokenizer using HuggingFace tokenizers (fast Rust implementation)."""
    print(f"Loading corpus from {corpus_path}...")
    path = Path(corpus_path)
    text = path.read_text(encoding="utf-8")
    print(f"Total characters: {len(text):,}")
    
    # Write to a temp file for the trainer
    temp_file = Path("temp_corpus.txt")
    temp_file.write_text(text, encoding="utf-8")
    
    # Initialize tokenizer
    tokenizer = Tokenizer(models.BPE(unk_token="<UNK>"))
    
    # Pre-tokenizer: split on whitespace and punctuation
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    
    # Decoder
    tokenizer.decoder = decoders.ByteLevel()
    
    # Post-processor for special tokens
    special_tokens = ["<PAD>", "<BOS>", "<EOS>", "<UNK>",
                      "<OBSERVE>", "</OBSERVE>",
                      "<RELATE>", "</RELATE>",
                      "<PLAN>", "</PLAN>",
                      "<VERIFY>", "</VERIFY>",
                      "<ANSWER>", "</ANSWER>",
                      "<TOOL_CALL>", "</TOOL_CALL>",
                      "<TOOL_RESULT>", "</TOOL_RESULT>",
                      "<TOOL_ERROR>", "</TOOL_ERROR>",
                      "<GRID>", "</GRID>",
                      "<OBJ>", "</OBJ>",
                      "<REL>", "</REL>",
                      "<TRANSFORM>", "</TRANSFORM>",
                      "<MEMORY>", "</MEMORY>",
                      "<RECALL>", "</RECALL>"]
    
    tokenizer.post_processor = processors.TemplateProcessing(
        single="<BOS> $A <EOS>",
        pair="<BOS> $A <EOS> $B:1 <EOS>:1",
        special_tokens=[(t, i) for i, t in enumerate(special_tokens)]
    )
    
    # Trainer
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        special_tokens=special_tokens,
        min_frequency=2,
        show_progress=True
    )
    
    print(f"Training BPE tokenizer with vocab_size={vocab_size} (fast Rust backend)...")
    tokenizer.train([str(temp_file)], trainer)
    
    # Save
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    tokenizer.save(str(output_path / "tokenizer.json"))
    
    # Also save in our format for compatibility
    vocab = tokenizer.get_vocab()
    merges = []
    # Note: HuggingFace tokenizers doesn't expose merges directly in a simple way
    # We'll save the vocab and create a manifest
    
    manifest = {
        "algorithm": "byte-level-bpe (huggingface tokenizers)",
        "vocab_size": len(vocab),
        "corpus_version": "hercule-100m-v2",
        "normalization": "byte-level",
        "specials": {t: vocab.get(t, -1) for t in special_tokens},
        "checksum": "hf-tokenizer"
    }
    
    (output_path / "tokenizer.manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    
    # Clean up temp file
    temp_file.unlink(missing_ok=True)
    
    print(f"Saved tokenizer to {output_dir}")
    print(f"Vocab size: {len(vocab)}")
    
    # Test
    test_text = "Hello, world! This is a test of the HERCULE 100M tokenizer."
    encoding = tokenizer.encode(test_text)
    print(f"\nTest encode/decode:")
    print(f"  Input:    {test_text}")
    print(f"  Tokens:   {encoding.ids}")
    print(f"  Decoded:  {tokenizer.decode(encoding.ids)}")
    
    return tokenizer


def main():
    parser = argparse.ArgumentParser(description="Train fast 32K+ vocab tokenizer using HF tokenizers")
    parser.add_argument("--corpus", default="training/data/large_corpus/tokenizer_corpus_100m.txt",
                        help="Path to corpus text file")
    parser.add_argument("--vocab-size", type=int, default=32768, help="Target vocabulary size")
    parser.add_argument("--output-dir", default="training/tokenizer/hercule-bpe-100m-v2-fast",
                        help="Output directory for tokenizer")
    args = parser.parse_args()
    
    train_fast_tokenizer(args.corpus, args.vocab_size, args.output_dir)


if __name__ == "__main__":
    main()