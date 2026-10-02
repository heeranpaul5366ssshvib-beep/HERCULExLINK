#!/usr/bin/env python3
"""HERCULE tokenizer wrapper for HuggingFace tokenizers (fast Rust backend)."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from tokenizers import Tokenizer as HFTokenizer
except ImportError:
    HFTokenizer = None


class HuggingFaceTokenizerWrapper:
    """Wrapper to make HF tokenizer compatible with HERCULE tokenizer interface."""
    
    # Core specials (match HERCULE tokenizer IDs)
    PAD, BOS, EOS, UNK = "<PAD>", "<BOS>", "<EOS>", "<UNK>"
    CORE_SPECIALS = [PAD, BOS, EOS, UNK]
    
    # Extended specials
    REASONING_SPECIALS = [
        "<OBSERVE>", "</OBSERVE>",
        "<RELATE>", "</RELATE>",
        "<PLAN>", "</PLAN>",
        "<VERIFY>", "</VERIFY>",
        "<ANSWER>", "</ANSWER>",
    ]
    
    TOOL_SPECIALS = [
        "<TOOL_CALL>", "</TOOL_CALL>",
        "<TOOL_RESULT>", "</TOOL_RESULT>",
        "<TOOL_ERROR>", "</TOOL_ERROR>",
    ]
    
    ARC_SPECIALS = [
        "<GRID>", "</GRID>",
        "<OBJ>", "</OBJ>",
        "<REL>", "</REL>",
        "<TRANSFORM>", "</TRANSFORM>",
    ]
    
    MEMORY_SPECIALS = [
        "<MEMORY>", "</MEMORY>",
        "<RECALL>", "</RECALL>",
    ]
    
    EXTENDED_SPECIALS = REASONING_SPECIALS + TOOL_SPECIALS + ARC_SPECIALS + MEMORY_SPECIALS
    ALL_SPECIALS = CORE_SPECIALS + EXTENDED_SPECIALS
    
    ALGORITHM = "byte-level-bpe (huggingface tokenizers)"
    NORMALIZATION = "byte-level"
    
    def __init__(self, tokenizer: HFTokenizer, vocab: Dict[str, int], specials: Optional[List[str]] = None):
        self._tokenizer = tokenizer
        self._vocab = dict(vocab)
        self._inv_vocab = {i: t for t, i in vocab.items()}
        self.specials = specials or self.ALL_SPECIALS
        self._special_ids = {s: self._vocab.get(s) for s in self.specials if s in self._vocab}
        self.corpus_version = "hercule-100m-v2"
    
    @property
    def vocab_size(self) -> int:
        return len(self._vocab)

    @property
    def merges(self) -> list:
        # Compatibility shim: HF backend doesn't expose merge list;
        # vocab_size - base gives the effective merge count.
        base = len(self.specials) + 256
        return [None] * max(0, self.vocab_size - base)
    
    @property
    def pad_id(self) -> int:
        return self._special_ids.get(self.PAD, 0)
    
    @property
    def bos_id(self) -> int:
        return self._special_ids.get(self.BOS, 1)
    
    @property
    def eos_id(self) -> int:
        return self._special_ids.get(self.EOS, 2)
    
    @property
    def unk_id(self) -> int:
        return self._special_ids.get(self.UNK, 3)
    
    def special_id(self, name: str) -> Optional[int]:
        return self._special_ids.get(name)
    
    def special_ids(self, names: List[str]) -> List[int]:
        return [self._special_ids[n] for n in names if n in self._special_ids]
    
    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> List[int]:
        encoding = self._tokenizer.encode(text)
        ids = encoding.ids
        if add_bos:
            ids = [self.bos_id] + ids
        if add_eos:
            ids = ids + [self.eos_id]
        return ids
    
    def decode(self, ids: List[int], skip_specials: bool = True) -> str:
        # Filter specials if requested
        if skip_specials:
            special_ids = set(self._special_ids.values())
            ids = [i for i in ids if i not in special_ids]
        return self._tokenizer.decode(ids)
    
    def decode_with_specials(self, ids: List[int]) -> str:
        return self._tokenizer.decode(ids)
    
    def checksum(self) -> str:
        import hashlib
        blob = json.dumps({"vocab_size": self.vocab_size, "algorithm": self.ALGORITHM,
                           "corpus": self.corpus_version}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
    
    def manifest(self) -> dict:
        return {"algorithm": self.ALGORITHM, "vocab_size": self.vocab_size,
                "corpus_version": self.corpus_version,
                "normalization": self.NORMALIZATION,
                "specials": {s: self._special_ids.get(s, -1) for s in self.specials},
                "checksum": self.checksum()}
    
    def save(self, directory: str) -> str:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        self._tokenizer.save(str(target / "tokenizer.json"))
        (target / "tokenizer.manifest.json").write_text(
            json.dumps(self.manifest(), indent=1), encoding="utf-8")
        return str(target / "tokenizer.json")
    
    @classmethod
    def load(cls, directory: str) -> "HuggingFaceTokenizerWrapper":
        hf_tok = HFTokenizer.from_file(str(Path(directory) / "tokenizer.json"))
        vocab = hf_tok.get_vocab()
        return cls(hf_tok, vocab)
    
    # N9: Number-aware encoding helpers
    def encode_number(self, n: int) -> List[int]:
        s = str(n)
        encoded = self.encode(s)
        if len(encoded) == 1 and encoded[0] != self.unk_id:
            return encoded
        return [self._vocab.get(d, self.unk_id) for d in s]
    
    def encode_grid(self, grid: List[List[int]]) -> List[int]:
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
        import json as _json
        ids = []
        if "<TOOL_CALL>" in self._special_ids:
            ids.append(self._special_ids["<TOOL_CALL>"])
        ids.extend(self.encode(f'{{"tool": "{tool}", "arguments": {_json.dumps(args)}}}'))
        if "</TOOL_CALL>" in self._special_ids:
            ids.append(self._special_ids["</TOOL_CALL>"])
        return ids


def load_hf_tokenizer(directory: str) -> HuggingFaceTokenizerWrapper:
    """Convenience function to load HF tokenizer wrapper."""
    return HuggingFaceTokenizerWrapper.load(directory)