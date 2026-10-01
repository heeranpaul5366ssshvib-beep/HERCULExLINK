from __future__ import annotations
"""HERCULE-LM model configurations (N9 §2).

Unified configuration system with named presets. Every size is an
explicit JSON document: no hidden dimensions, no pretrained shapes.
Parameter counts are computed, never asserted. No configuration implies
the model has been trained.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_DIR = Path(__file__).resolve().parent / "configs"


@dataclass
class HerculeLMConfig:
    """Complete model configuration. All fields are explicit."""
    model_id: str = "hercule-lm-nano"
    vocab_size: int = 512
    hidden_size: int = 96
    num_layers: int = 3
    num_heads: int = 6
    ffn_size: int = 384
    context_length: int = 64
    positional: str = "learned"          # learned | rope | alibi
    normalization: str = "layernorm"     # layernorm | rmsnorm
    activation: str = "gelu"             # gelu | silu | geglu
    dropout: float = 0.0
    initialization: str = "xavier-uniform"  # xavier-uniform | normal
    dtype: str = "float32"
    tokenizer_id: str = "hercule-bpe-nano-v1"
    # N9 extensions
    tied_embeddings: bool = False
    rope_theta: float = 10000.0
    rope_scaling: Optional[Dict] = None
    qkv_bias: bool = True
    out_bias: bool = True
    ffn_bias: bool = True
    norm_eps: float = 1e-5
    # Training defaults (can be overridden at runtime)
    optimizer: str = "adamw"
    lr: float = 3e-4
    weight_decay: float = 0.01
    beta1: float = 0.9
    beta2: float = 0.999
    eps: float = 1e-8
    grad_clip: float = 1.0
    warmup_steps: int = 50
    lr_schedule: str = "cosine"          # cosine | constant | linear_decay
    min_lr_ratio: float = 0.1

    def validate(self) -> None:
        if self.hidden_size % self.num_heads != 0:
            raise ValueError("hidden_size must be divisible by num_heads")
        if self.vocab_size < 260 or self.hidden_size < 8 or self.num_layers < 1:
            raise ValueError("degenerate model configuration")
        if self.context_length < 4:
            raise ValueError("context_length too small")
        if self.positional not in ("learned", "rope", "alibi"):
            raise ValueError(f"unknown positional: {self.positional}")
        if self.normalization not in ("layernorm", "rmsnorm"):
            raise ValueError(f"unknown normalization: {self.normalization}")
        if self.activation not in ("gelu", "silu", "geglu"):
            raise ValueError(f"unknown activation: {self.activation}")
        if self.initialization not in ("xavier-uniform", "normal"):
            raise ValueError(f"unknown initialization: {self.initialization}")
        if self.lr_schedule not in ("cosine", "constant", "linear_decay"):
            raise ValueError(f"unknown lr_schedule: {self.lr_schedule}")
        if self.tied_embeddings and self.vocab_size != self.hidden_size:
            # Tied embeddings require vocab_size == hidden_size for output projection
            # This is a soft constraint; we allow but warn via docs
            pass

    def parameter_count(self) -> int:
        """Exact count matching model.py's parameter layout."""
        d, v, L, f, c = (self.hidden_size, self.vocab_size,
                         self.num_layers, self.ffn_size, self.context_length)
        # Embeddings
        tok_params = v * d
        pos_params = c * d if self.positional == "learned" else 0
        # Per layer
        qkv_params = d * 3 * d + (3 * d if self.qkv_bias else 0)
        attn_out_params = d * d + (d if self.out_bias else 0)
        # FFN hidden size depends on activation
        ffn_hidden = f * 2 if self.activation == "geglu" else f
        ffn_params = d * ffn_hidden + (ffn_hidden if self.ffn_bias else 0) + f * d + (d if self.ffn_bias else 0)
        # Norm params: layernorm has 2*d (W+b), rmsnorm has d (W only)
        if self.normalization == "layernorm":
            ln_params = 4 * d  # ln1W, ln1b, ln2W, ln2b
        else:
            ln_params = 2 * d  # ln1W, ln2W (no bias)
        per_layer = qkv_params + attn_out_params + ffn_params + ln_params
        # Final norm
        final_norm = 2 * d if self.normalization == "layernorm" else d
        # Output head
        head_params = d * v + (v if self.out_bias else 0)
        if self.tied_embeddings:
            head_params = 0
        total = tok_params + pos_params + L * per_layer + final_norm + head_params
        return int(total)

    def architecture_hash(self) -> str:
        """Hash of architecture-defining fields only (excludes training hyperparams)."""
        arch_fields = {k: v for k, v in asdict(self).items()
                       if k not in ("optimizer", "lr", "weight_decay", "beta1", "beta2",
                                    "eps", "grad_clip", "warmup_steps", "lr_schedule",
                                    "min_lr_ratio", "tokenizer_id")}
        blob = json.dumps(arch_fields, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    def as_dict(self) -> dict:
        data = asdict(self)
        data["parameter_count"] = self.parameter_count()
        data["architecture_hash"] = self.architecture_hash()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "HerculeLMConfig":
        known = set(cls.__dataclass_fields__)
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        cfg.validate()
        return cfg

    @classmethod
    def from_preset(cls, name: str) -> "HerculeLMConfig":
        """Load a named preset configuration."""
        presets = {
            "nano": dict(model_id="hercule-lm-nano", vocab_size=512, hidden_size=128,
                         num_layers=4, num_heads=4, ffn_size=512, context_length=64,
                         tokenizer_id="hercule-bpe-nano-v1"),
            "micro": dict(model_id="hercule-lm-micro", vocab_size=1024, hidden_size=192,
                          num_layers=6, num_heads=6, ffn_size=768, context_length=128,
                          tokenizer_id="hercule-bpe-micro-v1"),
            "small": dict(model_id="hercule-lm-small", vocab_size=2048, hidden_size=256,
                          num_layers=12, num_heads=8, ffn_size=1024, context_length=256,
                          positional="rope", tied_embeddings=True, tokenizer_id="hercule-bpe-small-v1"),
            "medium": dict(model_id="hercule-lm-medium", vocab_size=4096, hidden_size=384,
                           num_layers=16, num_heads=8, ffn_size=1536, context_length=512,
                           positional="rope", tied_embeddings=True, tokenizer_id="hercule-bpe-medium-v1"),
            "100m": dict(model_id="hercule-lm-100m", vocab_size=16384, hidden_size=640,
                         num_layers=16, num_heads=10, ffn_size=2560, context_length=512,
                         positional="rope", tied_embeddings=True, tokenizer_id="hercule-bpe-100m-v1"),
            "300m": dict(model_id="hercule-lm-300m", vocab_size=32768, hidden_size=768,
                         num_layers=24, num_heads=12, ffn_size=3072, context_length=1024,
                         positional="rope", tied_embeddings=True, tokenizer_id="hercule-bpe-300m-v1"),
        }
        key = name.lower().replace("hercule-lm-", "").replace("hercule-", "")
        if key not in presets:
            raise ValueError(f"Unknown preset: {name}. Available: {list(presets.keys())}")
        return cls(**presets[key])

    def to_json_file(self, path: str) -> None:
        """Save configuration to JSON file."""
        Path(path).write_text(json.dumps(self.as_dict(), indent=1), encoding="utf-8")


# Named model configurations (presets)
# NOTE: Existence of a preset does NOT imply the model has been trained.
MODEL_PRESETS: Dict[str, Dict] = {
    "HERCULE-NANO": {
        "model_id": "hercule-lm-nano",
        "vocab_size": 512, "hidden_size": 128, "num_layers": 4, "num_heads": 4,
        "ffn_size": 512, "context_length": 64,
        "positional": "learned", "normalization": "layernorm", "activation": "gelu",
        "dropout": 0.0, "initialization": "xavier-uniform", "dtype": "float32",
        "tokenizer_id": "hercule-bpe-nano-v1",
        "tied_embeddings": False,
    },
    "HERCULE-MICRO": {
        "model_id": "hercule-lm-micro",
        "vocab_size": 1024, "hidden_size": 192, "num_layers": 6, "num_heads": 6,
        "ffn_size": 768, "context_length": 128,
        "positional": "learned", "normalization": "layernorm", "activation": "gelu",
        "dropout": 0.0, "initialization": "xavier-uniform", "dtype": "float32",
        "tokenizer_id": "hercule-bpe-micro-v1",
        "tied_embeddings": False,
    },
    "HERCULE-SMALL": {
        "model_id": "hercule-lm-small",
        "vocab_size": 2048, "hidden_size": 256, "num_layers": 12, "num_heads": 8,
        "ffn_size": 1024, "context_length": 256,
        "positional": "rope", "normalization": "rmsnorm", "activation": "silu",
        "dropout": 0.1, "initialization": "xavier-uniform", "dtype": "float32",
        "tokenizer_id": "hercule-bpe-small-v1",
        "tied_embeddings": True, "rope_theta": 10000.0,
    },
    "HERCULE-MEDIUM": {
        "model_id": "hercule-lm-medium",
        "vocab_size": 4096, "hidden_size": 384, "num_layers": 16, "num_heads": 8,
        "ffn_size": 1536, "context_length": 512,
        "positional": "rope", "normalization": "rmsnorm", "activation": "silu",
        "dropout": 0.1, "initialization": "xavier-uniform", "dtype": "float32",
        "tokenizer_id": "hercule-bpe-medium-v1",
        "tied_embeddings": True, "rope_theta": 10000.0,
    },
    "HERCULE-100M": {
        "model_id": "hercule-lm-100m",
        "vocab_size": 16384, "hidden_size": 640, "num_layers": 16, "num_heads": 10,
        "ffn_size": 2560, "context_length": 512,
        "positional": "rope", "normalization": "rmsnorm", "activation": "silu",
        "dropout": 0.1, "initialization": "xavier-uniform", "dtype": "float32",
        "tokenizer_id": "hercule-bpe-100m-v1",
        "tied_embeddings": True, "rope_theta": 10000.0,
    },
    "HERCULE-300M": {
        "model_id": "hercule-lm-300m",
        "vocab_size": 32768, "hidden_size": 768, "num_layers": 24, "num_heads": 12,
        "ffn_size": 3072, "context_length": 1024,
        "positional": "rope", "normalization": "rmsnorm", "activation": "silu",
        "dropout": 0.1, "initialization": "xavier-uniform", "dtype": "float32",
        "tokenizer_id": "hercule-bpe-300m-v1",
        "tied_embeddings": True, "rope_theta": 10000.0,
    },
}


def get_preset(name: str) -> HerculeLMConfig:
    """Get a preset configuration by name (case-insensitive)."""
    key = name.upper()
    if key not in MODEL_PRESETS:
        raise ValueError(f"Unknown preset {name!r}. Available: {list(MODEL_PRESETS.keys())}")
    return HerculeLMConfig(**MODEL_PRESETS[key])


def list_presets() -> List[str]:
    return list(MODEL_PRESETS.keys())


def load_config(name_or_path: str) -> HerculeLMConfig:
    """Load config from file, preset name, or JSON path."""
    # Try as preset first
    try:
        return get_preset(name_or_path)
    except ValueError:
        pass
    # Try as file path
    path = Path(name_or_path)
    if not path.is_file():
        path = CONFIG_DIR / (name_or_path if name_or_path.endswith(".json")
                             else name_or_path + ".json")
    return HerculeLMConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
