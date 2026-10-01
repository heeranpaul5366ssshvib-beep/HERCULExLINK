"""
N10.2 Data Pipeline Fix
========================
Fixes the data pathology identified in N10.1 collapse diagnosis.

Targets:
- >= 500,000 training tokens (preferred 1,000,000+)
- Duplicate rate < 5%
- Vocabulary coverage > 90%
- Space + newline < 10%
- Whitespace < 20%
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from models.hercule_lm.data import (
    DataSource, Document, load_documents, split_documents,
    validate_documents, check_no_leakage, dataset_manifest,
    encode_split, near_duplicates, quality_dimensions
)
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm.config import get_preset
from models.hercule_lm.synthetic_reasoning import generate_curriculum


@dataclass
class PipelineReport:
    """Report on data pipeline transformation."""
    stage: str
    documents_before: int
    documents_after: int
    tokens_before: int
    tokens_after: int
    duplicates_removed: int
    duplicate_rate_before: float
    duplicate_rate_after: float
    vocab_coverage_before: float
    vocab_coverage_after: float
    whitespace_ratio_before: float
    whitespace_ratio_after: float
    details: Dict[str, Any] = field(default_factory=dict)


def load_and_analyze_corpus(
    corpus_dir: str,
    sources_path: str,
    tokenizer: HerculeBPETokenizer,
    paragraphs: bool = True,
    docs: Optional[List[Document]] = None
) -> Tuple[List[Document], Dict[str, Any]]:
    """Load corpus and analyze its properties. If docs provided, use them directly."""
    if docs is None:
        sources = [DataSource(**s) for s in json.loads(Path(sources_path).read_text())]
        docs = load_documents(corpus_dir, sources, paragraphs=True)
    
    # Analyze
    all_texts = [d.text for d in docs]
    total_chars = sum(len(t) for t in all_texts)
    
    # Tokenize
    all_tokens = []
    for text in all_texts:
        ids = tokenizer.encode(text)
        if ids:
            ids = ids[:-1]  # Remove EOS for analysis
        all_tokens.extend(ids)
    
    freq = Counter(all_tokens)
    total_tokens = len(all_tokens)
    unique_tokens = len(freq)
    vocab_size = tokenizer.vocab_size
    vocab_coverage = unique_tokens / vocab_size
    
    # Whitespace analysis
    space_count = freq.get(tokenizer.encode(" ")[0], 0) if tokenizer.encode(" ") else 0
    newline_count = freq.get(tokenizer.encode("\n")[0], 0) if tokenizer.encode("\n") else 0
    space_newline = space_count + newline_count
    whitespace_ratio = space_newline / total_tokens if total_tokens > 0 else 0
    
    # Duplicates
    unique_texts = set(d.text for d in docs)
    duplicate_rate = 1.0 - len(unique_texts) / len(docs) if docs else 0
    
    stats = {
        "total_documents": len(docs),
        "unique_documents": len(unique_texts),
        "duplicate_rate": duplicate_rate,
        "total_tokens": total_tokens,
        "unique_tokens": unique_tokens,
        "vocab_size": vocab_size,
        "vocab_coverage": vocab_coverage,
        "total_chars": total_chars,
        "whitespace_ratio": whitespace_ratio,
        "space_count": space_count,
        "newline_count": newline_count,
        "top_tokens": dict(freq.most_common(30)),
    }
    
    return docs, stats


def deduplicate_documents(docs: List[Document]) -> Tuple[List[Document], Dict[str, Any]]:
    """Remove exact duplicate documents."""
    seen_hashes = set()
    seen_texts = set()
    unique_docs = []
    duplicates = 0
    
    for doc in docs:
        text_hash = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
        if text_hash in seen_texts:
            duplicates += 1
            continue
        seen_texts.add(text_hash)
        unique_docs.append(doc)
    
    report = {
        "documents_before": len(docs),
        "documents_after": len(unique_docs),
        "duplicates_removed": duplicates,
        "duplicate_rate_before": 1.0 - len(set(d.text for d in docs)) / len(docs) if docs else 0,
        "duplicate_rate_after": 0.0,
    }
    return unique_docs, report


def generate_additional_data(
    tokenizer: HerculeBPETokenizer,
    target_tokens: int,
    current_tokens: int,
    seed: int = 42
) -> List[Document]:
    """Generate additional synthetic data to reach target token count."""
    needed = max(0, target_tokens - current_tokens)
    if needed <= 0:
        return []
    
    print(f"Generating ~{needed} additional tokens...")
    
    additional_docs = []
    
    # Use curriculum generator to create diverse data
    from models.hercule_lm.synthetic_reasoning import (
        generate_arithmetic, generate_comparison, generate_sequence,
        generate_symbolic_transform, generate_code, generate_tool_use,
        generate_verification, generate_arc_grid
    )
    
    generators = [
        ("arithmetic", generate_arithmetic),
        ("comparison", generate_comparison),
        ("sequence", generate_sequence),
        ("symbolic_transform", generate_symbolic_transform),
        ("code", generate_code),
        ("tool_use", generate_tool_use),
        ("verification", generate_verification),
        ("arc_grid", generate_arc_grid),
    ]
    
    additional_docs = []
    current_additional_tokens = 0
    seed_offset = 10000
    
    # Generate much more data - multiple passes with different seeds
    for domain, gen_fn in generators:
        for difficulty in range(1, 6):  # Up to difficulty 5
            if current_additional_tokens >= needed:
                break
            for seed_variant in range(8):  # 8 different seeds per difficulty
                if current_additional_tokens >= needed:
                    break
                examples = gen_fn(seed_offset + seed_variant * 1000 + difficulty * 100, difficulty)
                seed_offset += 10000
                
                for ex in examples:
                    doc = Document(
                        doc_id=f"synthetic:{domain}:{difficulty}:seed{seed_variant}:{ex.generation_seed}",
                        source="hercule-synthetic",
                        license="HERCULE-authored (MIT, repo)",
                        text=f"Q: {ex.problem}\nA: {ex.target}\n"
                    )
                    additional_docs.append(doc)
                    current_additional_tokens += len(tokenizer.encode(doc.text))
                    
                    if current_additional_tokens >= needed:
                        break
            if current_additional_tokens >= needed:
                break
    
    print(f"Generated {len(additional_docs)} additional documents (~{current_additional_tokens} tokens)")
    return additional_docs


def balance_whitespace(docs: List[Document], tokenizer: HerculeBPETokenizer) -> Tuple[List[Document], Dict[str, Any]]:
    """Balance whitespace in documents without destroying structure."""
    # For now, just report - we don't want to destructively modify structured data
    # The real fix is generating more diverse data
    
    # Analyze current whitespace
    all_text = "".join(d.text for d in docs)
    space_count = all_text.count(" ")
    newline_count = all_text.count("\n")
    total_chars = len(all_text)
    whitespace_ratio = (space_count + newline_count) / max(1, total_chars)
    
    report = {
        "whitespace_ratio": whitespace_ratio,
        "space_count": space_count,
        "newline_count": newline_count,
        "total_chars": total_chars,
    }
    return docs, report


def load_and_analyze_corpus(
    corpus_dir: str,
    sources_path: str,
    tokenizer: HerculeBPETokenizer,
    paragraphs: bool = True,
    docs: Optional[List[Document]] = None
) -> Tuple[List[Document], Dict[str, Any]]:
    """Load corpus and analyze its properties. If docs provided, use them directly."""
    if docs is None:
        sources = [DataSource(**s) for s in json.loads(Path(sources_path).read_text())]
        docs = load_documents(corpus_dir, sources, paragraphs=True)
    
    # Analyze
    all_texts = [d.text for d in docs]
    total_chars = sum(len(t) for t in all_texts)
    
    # Tokenize
    all_tokens = []
    for text in all_texts:
        ids = tokenizer.encode(text)
        if ids:
            ids = ids[:-1]  # Remove EOS for analysis
        all_tokens.extend(ids)
    
    freq = Counter(all_tokens)
    total_tokens = len(all_tokens)
    unique_tokens = len(freq)
    vocab_size = tokenizer.vocab_size
    vocab_coverage = unique_tokens / vocab_size
    
    # Whitespace analysis
    space_count = freq.get(tokenizer.encode(" ")[0], 0) if tokenizer.encode(" ") else 0
    newline_count = freq.get(tokenizer.encode("\n")[0], 0) if tokenizer.encode("\n") else 0
    space_newline = space_count + newline_count
    whitespace_ratio = space_newline / total_tokens if total_tokens > 0 else 0
    
    # Duplicates
    unique_texts = set(d.text for d in docs)
    duplicate_rate = 1.0 - len(unique_texts) / len(docs) if docs else 0
    
    stats = {
        "total_documents": len(docs),
        "unique_documents": len(unique_texts),
        "duplicate_rate": duplicate_rate,
        "total_tokens": total_tokens,
        "unique_tokens": unique_tokens,
        "vocab_size": vocab_size,
        "vocab_coverage": vocab_coverage,
        "total_chars": total_chars,
        "whitespace_ratio": whitespace_ratio,
        "space_count": space_count,
        "newline_count": newline_count,
        "top_tokens": dict(freq.most_common(30)),
    }
    
    return docs, stats


def deduplicate_documents(docs: List[Document]) -> Tuple[List[Document], Dict[str, Any]]:
    """Remove exact duplicate documents."""
    seen_hashes = set()
    seen_texts = set()
    unique_docs = []
    duplicates = 0
    
    for doc in docs:
        text_hash = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
        if text_hash in seen_texts:
            duplicates += 1
            continue
        seen_texts.add(text_hash)
        unique_docs.append(doc)
    
    report = {
        "documents_before": len(docs),
        "documents_after": len(unique_docs),
        "duplicates_removed": duplicates,
        "duplicate_rate_before": 1.0 - len(set(d.text for d in docs)) / len(docs) if docs else 0,
        "duplicate_rate_after": 0.0,
    }
    return unique_docs, report


def balance_whitespace(docs: List[Document], tokenizer: HerculeBPETokenizer) -> Tuple[List[Document], Dict[str, Any]]:
    """Balance whitespace in documents without destroying structure."""
    # For now, just report - we don't want to destructively modify structured data
    # The real fix is generating more diverse data
    
    # Analyze current whitespace
    all_text = "".join(d.text for d in docs)
    space_count = all_text.count(" ")
    newline_count = all_text.count("\n")
    total_chars = len(all_text)
    whitespace_ratio = (space_count + newline_count) / max(1, total_chars)
    
    report = {
        "whitespace_ratio": whitespace_ratio,
        "space_count": space_count,
        "newline_count": newline_count,
        "total_chars": total_chars,
    }
    return docs, report


def build_fixed_dataset(
    corpus_dir: str,
    sources_path: str,
    output_dir: str,
    tokenizer: HerculeBPETokenizer,
    target_tokens: int = 1000000,
    seed: int = 42
) -> Tuple[List[Document], Dict[str, Any]]:
    """Build a fixed dataset with all fixes applied."""
    
    print("=" * 60)
    print("N10.2 DATA PIPELINE FIX")
    print("=" * 60)
    
    # Step 1: Load and analyze original
    print("\n1. Loading and analyzing original corpus...")
    docs, orig_stats = load_and_analyze_corpus(
        corpus_dir, 
        sources_path,
        tokenizer,
        paragraphs=True
    )
    print(f"   Original: {orig_stats['total_documents']} docs, {orig_stats['total_tokens']} tokens")
    print(f"   Vocab coverage: {orig_stats['vocab_coverage']:.1%}")
    print(f"   Duplicate rate: {orig_stats['duplicate_rate']:.1%}")
    print(f"   Whitespace ratio: {orig_stats['whitespace_ratio']:.1%}")
    
    # Step 2: Deduplicate
    print("\n2. Deduplicating documents...")
    docs, dedup_report = deduplicate_documents(docs)
    print(f"   Removed {dedup_report['duplicates_removed']} duplicates")
    print(f"   Duplicate rate: {dedup_report['duplicate_rate_before']:.1%} -> {dedup_report['duplicate_rate_after']:.1%}")
    
    # Step 3: Generate additional data
    print("\n3. Generating additional synthetic data...")
    current_tokens = sum(len(tokenizer.encode(d.text)) for d in docs)
    additional_docs = generate_additional_data(
        tokenizer, 
        target_tokens=max(0, 1000000 - sum(len(tokenizer.encode(d.text)) for d in docs)),
        current_tokens=current_tokens
    )
    docs.extend(additional_docs)
    print(f"   Added {len(additional_docs)} synthetic documents")
    
    # Step 4: Balance whitespace (analysis only)
    print("\n4. Analyzing whitespace balance...")
    docs, ws_report = balance_whitespace(docs, tokenizer)
    print(f"   Whitespace ratio: {ws_report['whitespace_ratio']:.1%}")
    
    # Step 5: Final analysis (using docs in memory)
    print("\n5. Final analysis...")
    all_texts = [d.text for d in docs]
    all_tokens = []
    for text in all_texts:
        all_tokens.extend(tokenizer.encode(text))
    freq = Counter(all_tokens)
    total = len(all_tokens)
    unique = len(freq)
    space_count = freq.get(tokenizer.encode(" ")[0], 0) if tokenizer.encode(" ") else 0
    newline_count = freq.get(tokenizer.encode("\n")[0], 0) if tokenizer.encode("\n") else 0
    ws_ratio = (space_count + newline_count) / total if total > 0 else 0
    vocab_cov = unique / tokenizer.vocab_size
    
    final_stats = {
        "total_documents": len(docs),
        "total_tokens": total,
        "unique_tokens": unique,
        "vocab_coverage": vocab_cov,
        "whitespace_ratio": ws_ratio,
    }
    
    print(f"   Final: {final_stats['total_documents']} docs, {final_stats['total_tokens']} tokens")
    print(f"   Vocab coverage: {final_stats['vocab_coverage']:.1%}")
    print(f"   Whitespace ratio: {final_stats['whitespace_ratio']:.1%}")
    
    # Save fixed dataset
    print("\n6. Saving fixed dataset...")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save as single combined file for simplicity
    combined_text = "\n\n".join(d.text for d in docs)
    (output_path / "fixed_corpus.txt").write_text(combined_text, encoding="utf-8")
    
    # Save metadata
    metadata = {
        "original_stats": orig_stats,
        "dedup_report": dedup_report,
        "whitespace_report": ws_report,
        "final_stats": final_stats,
        "generated_docs": len(additional_docs),
    }
    (output_path / "pipeline_report.json").write_text(json.dumps(metadata, indent=1), encoding="utf-8")
    
    print(f"\nFixed dataset saved to {output_dir}")
    print(f"Total tokens: {final_stats['total_tokens']}")
    print(f"Vocab coverage: {final_stats['vocab_coverage']:.1%}")
    print(f"Whitespace ratio: {final_stats['whitespace_ratio']:.1%}")
    
    return docs, metadata


def main():
    """Main entry point."""
    # Load tokenizer
    preset = get_preset("HERCULE-NANO")
    tokenizer = HerculeBPETokenizer.load(f"training/tokenizer/{preset.tokenizer_id}")
    
    # Build fixed dataset
    docs, metadata = build_fixed_dataset(
        corpus_dir="training/data/raw",
        sources_path="training/data/sources.json",
        output_dir="training/data/fixed",
        tokenizer=tokenizer,
        target_tokens=500000,
        seed=42
    )
    
    print("\n" + "=" * 60)
    print("DATA PIPELINE FIX COMPLETE")
    print("=" * 60)
    print(f"Output directory: training/data/fixed")
    print(f"Total documents: {len(docs)}")
    print(f"Total tokens: {metadata['final_stats']['total_tokens']}")
    print(f"Vocab coverage: {metadata['final_stats']['vocab_coverage']:.1%}")
    print(f"Whitespace ratio: {metadata['final_stats']['whitespace_ratio']:.1%}")


if __name__ == "__main__":
    main()