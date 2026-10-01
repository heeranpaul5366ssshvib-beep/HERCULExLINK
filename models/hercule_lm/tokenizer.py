from __future__ import annotations
"""HERCULE BPE tokenizer (N9): own implementation, own vocabulary.

Byte-level BPE trained from an explicit corpus: 256 byte tokens after
reserved specials, then learned merges. No pretrained tokenizer is
loaded or reused; the algorithm choice is recorded in the saved
tokenizer manifest. Deterministic given the same corpus and seed.

N9 Extensions:
- Extended special tokens for reasoning structures, tool calls, ARC grids
- Number tokenization improvements
- Configurable special token registry
"""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Core specials (always present, fixed IDs 0-3)
PAD, BOS, EOS, UNK = "<PAD>", "<BOS>", "<EOS>", "<UNK>"
CORE_SPECIALS = [PAD, BOS, EOS, UNK]

# N9 Extended specials for structured reasoning
REASONING_SPECIALS = [
    "<OBSERVE>", "</OBSERVE>",
    "<RELATE>", "</RELATE>",
    "<PLAN>", "</PLAN>",
    "<VERIFY>", "</VERIFY>",
    "<ANSWER>", "</ANSWER>",
]

# Tool call specials
TOOL_SPECIALS = [
    "<TOOL_CALL>", "</TOOL_CALL>",
    "<TOOL_RESULT>", "</TOOL_RESULT>",
    "<TOOL_ERROR>", "</TOOL_ERROR>",
]

# ARC grid specials
ARC_SPECIALS = [
    "<GRID>", "</GRID>",
    "<OBJ>", "</OBJ>",
    "<REL>", "</REL>",
    "<TRANSFORM>", "</TRANSFORM>",
]

# Memory specials
MEMORY_SPECIALS = [
    "<MEMORY>", "</MEMORY>",
    "<RECALL>", "</RECALL>",
]

# All extended specials
EXTENDED_SPECIALS = REASONING_SPECIALS + TOOL_SPECIALS + ARC_SPECIALS + MEMORY_SPECIALS
ALL_SPECIALS = CORE_SPECIALS + EXTENDED_SPECIALS

ALGORITHM = "byte-level-bpe"
NORMALIZATION = "none (raw UTF-8 bytes; whitespace significant)"


class HerculeBPETokenizer:
    def __init__(self, vocab: Optional[Dict[bytes, int]] = None,
                 merges: Optional[List[Tuple[bytes, bytes]]] = None,
                 corpus_version: str = "",
                 specials: Optional[List[str]] = None):
        self.vocab: Dict[bytes, int] = dict(vocab or {})
        self.merges: List[Tuple[bytes, bytes]] = list(merges or [])
        self.corpus_version = corpus_version
        self.specials = specials or ALL_SPECIALS
        self._rank = {pair: i for i, pair in enumerate(self.merges)}
        self._inv = {i: t for t, i in self.vocab.items()}
        self._special_ids = {s: self.vocab.get(s.encode()) for s in self.specials if s.encode() in self.vocab}

    # --------------------------------------------------
    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    @property
    def pad_id(self) -> int:
        return self._special_ids.get(PAD, 0)

    @property
    def bos_id(self) -> int:
        return self._special_ids.get(BOS, 1)

    @property
    def eos_id(self) -> int:
        return self._special_ids.get(EOS, 2)

    @property
    def unk_id(self) -> int:
        return self._special_ids.get(UNK, 3)

    def special_id(self, name: str) -> Optional[int]:
        """Get ID of a special token by name (e.g., '<OBSERVE>')."""
        return self._special_ids.get(name)

    def special_ids(self, names: List[str]) -> List[int]:
        """Get IDs of multiple special tokens."""
        return [self._special_ids[n] for n in names if n in self._special_ids]

    # --------------------------------------------------
    @classmethod
    def train(cls, texts: List[str], vocab_size: int = 512,
              corpus_version: str = "",
              specials: Optional[List[str]] = None) -> "HerculeBPETokenizer":
        """Train merges on a corpus. Pure-Python; corpora here are small."""
        specials = specials or ALL_SPECIALS
        vocab: Dict[bytes, int] = {s.encode(): i for i, s in enumerate(specials)}
        for byte in range(256):
            vocab[bytes([byte])] = len(vocab)
        words: Counter = Counter()
        for text in texts:
            for chunk in re.split(r"(\s+)", str(text or "")):
                if chunk:
                    words[tuple(bytes([b]) for b in chunk.encode("utf-8"))] += 1
        merges: List[Tuple[bytes, bytes]] = []
        while len(vocab) < vocab_size:
            pair_counts: Counter = Counter()
            for word, count in words.items():
                for i in range(len(word) - 1):
                    pair_counts[(word[i], word[i + 1])] += count
            if not pair_counts:
                break
            best = max(sorted(pair_counts), key=lambda p: pair_counts[p])
            merged = best[0] + best[1]
            if merged in vocab:
                break
            vocab[merged] = len(vocab)
            merges.append(best)
            merged_words: Counter = Counter()
            for word, count in words.items():
                out: List[bytes] = []
                i = 0
                while i < len(word):
                    if i < len(word) - 1 and (word[i], word[i + 1]) == best:
                        out.append(merged)
                        i += 2
                    else:
                        out.append(word[i])
                        i += 1
                merged_words[tuple(out)] += count
            words = merged_words
        tok = cls(vocab, merges, corpus_version, specials)
        return tok

    # --------------------------------------------------
    def _encode_word(self, word: bytes) -> List[int]:
        if not word:
            return []
        if word in self.vocab:
            return [self.vocab[word]]
        parts: List[bytes] = [bytes([b]) for b in word]
        while len(parts) > 1:
            best_rank, best_idx = None, -1
            for i in range(len(parts) - 1):
                rank = self._rank.get((parts[i], parts[i + 1]))
                if rank is not None and (best_rank is None or rank < best_rank):
                    best_rank, best_idx = rank, i
            if best_idx < 0:
                break
            parts = parts[:best_idx] + [parts[best_idx] + parts[best_idx + 1]] + parts[best_idx + 2:]
        ids = []
        for part in parts:
            ids.append(self.vocab.get(part, self.unk_id))
        return ids

    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> List[int]:
        ids: List[int] = []
        if add_bos:
            ids.append(self.bos_id)
        for chunk in re.split(r"(\s+)", str(text or "")):
            if not chunk:
                continue
            ids.extend(self._encode_word(chunk.encode("utf-8")))
        if add_eos:
            ids.append(self.eos_id)
        return ids

    def decode(self, ids: List[int], skip_specials: bool = True) -> str:
        chunks: List[bytes] = []
        specials_bytes = {s.encode() for s in self.specials}
        for i in ids:
            token = self._inv.get(int(i))
            if token is None:
                continue
            if skip_specials and token in specials_bytes:
                continue
            chunks.append(token)
        return b"".join(chunks).decode("utf-8", errors="replace")

    def decode_with_specials(self, ids: List[int]) -> str:
        """Decode including special tokens as their string representations."""
        chunks: List[str] = []
        for i in ids:
            token = self._inv.get(int(i))
            if token is None:
                continue
            try:
                chunks.append(token.decode("utf-8"))
            except UnicodeDecodeError:
                chunks.append(f"<BYTES:{token.hex()}>")
        return "".join(chunks)

    # --------------------------------------------------
    def checksum(self) -> str:
        blob = json.dumps({"vocab": sorted(self.vocab.values()),
                           "merges": len(self.merges),
                           "algorithm": ALGORITHM,
                           "corpus": self.corpus_version,
                           "specials": self.specials}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def manifest(self) -> dict:
        return {"algorithm": ALGORITHM, "vocab_size": self.vocab_size,
                "merges": len(self.merges), "corpus_version": self.corpus_version,
                "normalization": NORMALIZATION,
                "specials": {s: self.vocab.get(s.encode(), -1) for s in self.specials},
                "checksum": self.checksum()}

    def save(self, directory: str) -> str:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        payload = {"algorithm": ALGORITHM, "corpus_version": self.corpus_version,
                   "specials": self.specials,
                   "vocab": {t.decode("utf-8", errors="surrogateescape"): i
                             for t, i in self.vocab.items()},
                   "merges": [[a.decode("utf-8", errors="surrogateescape"),
                               b.decode("utf-8", errors="surrogateescape")]
                              for a, b in self.merges]}
        (target / "tokenizer.json").write_text(
            json.dumps(payload, ensure_ascii=True, indent=1), encoding="utf-8")
        (target / "tokenizer.manifest.json").write_text(
            json.dumps(self.manifest(), indent=1), encoding="utf-8")
        return str(target / "tokenizer.json")

    @classmethod
    def load(cls, directory: str) -> "HerculeBPETokenizer":
        payload = json.loads((Path(directory) / "tokenizer.json").read_text(encoding="utf-8"))

        def _enc(s: str) -> bytes:
            return s.encode("utf-8", errors="surrogateescape")

        vocab = {_enc(t): int(i) for t, i in payload["vocab"].items()}
        merges = [(_enc(a), _enc(b)) for a, b in payload["merges"]]
        specials = payload.get("specials", ALL_SPECIALS)
        return cls(vocab, merges, payload.get("corpus_version", ""), specials)

    # --------------------------------------------------
    # N9: Number-aware encoding helpers
    def encode_number(self, n: int) -> List[int]:
        """Encode an integer as a single token if in vocab, else digit-by-digit."""
        s = str(n)
        encoded = self.encode(s)
        # If the whole number is a single token, use it
        if len(encoded) == 1 and encoded[0] != self.unk_id:
            return encoded
        # Otherwise encode digit by digit for better compositionality
        return [self.vocab.get(bytes([ord(d)]), self.unk_id) for d in s]

    def encode_grid(self, grid: List[List[int]]) -> List[int]:
        """Encode an ARC-style grid with structural tokens."""
        ids = []
        if "<GRID>" in self._special_ids:
            ids.append(self._special_ids["<GRID>"])
        for row in grid:
            for val in row:
                ids.extend(self.encode_number(val))
        if "</GRID>" in self._special_ids:
            ids.append(self._special_ids["</GRID>"])
        return ids

    def encode_tool_call(self, tool: str, args: dict) -> List[int]:
        """Encode a structured tool call."""
        ids = []
        if "<TOOL_CALL>" in self._special_ids:
            ids.append(self._special_ids["<TOOL_CALL>"])
        ids.extend(self.encode(f'{{"tool": "{tool}", "arguments": {json.dumps(args)}}}'))
        if "</TOOL_CALL>" in self._special_ids:
            ids.append(self._special_ids["</TOOL_CALL>"])
        return ids


# --------------------------------------------------
# Convenience functions for N9 structured data generation
def create_reasoning_tokenizer(vocab_size: int = 2048, corpus_version: str = "") -> HerculeBPETokenizer:
    """Create a tokenizer with all N9 reasoning specials pre-registered."""
    # This creates an empty tokenizer with specials; meant to be trained later
    vocab = {s.encode(): i for i, s in enumerate(ALL_SPECIALS)}
    for byte in range(256):
        vocab[bytes([byte])] = len(vocab)
    return HerculeBPETokenizer(vocab=vocab, corpus_version=corpus_version)


def tokenize_arithmetic_expression(expr: str, tokenizer: HerculeBPETokenizer) -> List[int]:
    """Tokenize arithmetic expression with operator awareness."""
    # Simple approach: just encode normally, but could be enhanced
    return tokenizer.encode(expr)


def tokenize_arc_task(input_grid: List[List[int]], output_grid: List[List[int]],
                      tokenizer: HerculeBPETokenizer) -> List[int]:
    """Tokenize an ARC task as structured sequence."""
    ids = []
    if "<OBSERVE>" in tokenizer._special_ids:
        ids.append(tokenizer._special_ids["<OBSERVE>"])
    ids.extend(tokenizer.encode_grid(input_grid))
    if "</OBSERVE>" in tokenizer._special_ids:
        ids.append(tokenizer._special_ids["</OBSERVE>"])
    if "<ANSWER>" in tokenizer._special_ids:
        ids.append(tokenizer._special_ids["<ANSWER>"])
    ids.extend(tokenizer.encode_grid(output_grid))
    if "</ANSWER>" in tokenizer._special_ids:
        ids.append(tokenizer._special_ids["</ANSWER>"])
    return ids