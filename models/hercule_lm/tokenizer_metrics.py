from __future__ import annotations
"""Tokenizer measurements (frontier P4): fertility, compression, probes.

All measured on the given tokenizer + sample texts. No quality
claims beyond the numbers. Multilingual: byte-level BPE handles any
UTF-8 script; fertility is reported per sample, not certified.
"""

import re
from typing import Any, Dict, List


def measure(tokenizer, samples: List[str]) -> Dict[str, Any]:
    """Fertility (tok/word), compression (bytes/tok), round-trip rate."""
    total_words, total_toks, total_bytes, exact = 0, 0, 0, 0
    for text in samples:
        ids = tokenizer.encode(text)
        total_words += max(1, len(str(text).split()))
        total_toks += max(1, len(ids))
        total_bytes += max(1, len(str(text).encode("utf-8")))
        if tokenizer.decode(ids) == text:
            exact += 1
    return {
        "samples": len(samples),
        "fertility_tok_per_word": round(total_toks / total_words, 3),
        "compression_bytes_per_tok": round(total_bytes / total_toks, 3),
        "roundtrip_rate": round(exact / max(1, len(samples)), 3),
        "vocab_size": tokenizer.vocab_size,
    }


def probe_categories(tokenizer) -> Dict[str, Any]:
    """Code / numbers / punctuation / whitespace / multilingual probes."""
    probes = {
        "code": "def add(a, b):\n    return a + b",
        "numbers": "Calculate 317 + 542.",
        "punctuation": "Hello, world! (yes?) [no]; 'maybe'...",
        "whitespace": "a  b\n\tc",
        "multilingual": "Bonjour le monde. Hola mundo. ",
    }
    out = {}
    for name, text in probes.items():
        ids = tokenizer.encode(text)
        out[name] = {"tokens": len(ids),
                     "fertility": round(len(ids) / max(1, len(text.split())), 3),
                     "roundtrip": tokenizer.decode(ids) == text}
    return out
