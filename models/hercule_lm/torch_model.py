from __future__ import annotations
"""HERCULE-LM PyTorch backend (real autograd, CPU+CUDA).

Same architecture as :mod:`models.hercule_lm.model` (the NumPy
reference), independently implemented from scratch with
``torch` ops — never pretrained weights, random initialization
only:

- token embedding + positional embedding (learned/RoPE/ALiBi)
- N transformer blocks
- LayerNorm/RMSNorm (eps configurable)
- causal multi-head self-attention with residual
- Norm + Activation (GELU/SiLU/GeGLU) FFN with residual
- final Norm + LM output head + mean cross-entropy

QKV LAYOUT (load-bearing): each block holds a single packed
``qkvW`` shaped ``[hidden, 3*hidden]`` projected as
``h @ qkvW + qkvb``, reshaped to ``[B, T, num_heads, 3*head_dim]``
and split per head into ``[Qh, Kh, Vh]`` — exactly the NumPy
layout. Do NOT "improve" this into a different packing.

Parameter-name mapping: ``torch.nn.Module`` forbids ``'.'`` in
registered parameter names, so per-layer weights live on
``blocks[i].<name>`` (state_dict key ``blocks.<i>.<name>``) while
:meth:`numpy_param_dict` / :meth:`load_numpy_param_dict` translate
to/from the NumPy names (``L{i}.<name>``) for parity checks,
checkpoint conversion, and architecture-hash identity (the hash
comes from the shared :class:`HerculeLMConfig`, so it is identical
across backends by construction).
"""

import math

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except Exception as exc:
    raise ImportError(
        "PyTorch is required for the torch backend "
        "(pip install torch; CPU-only wheels are fine for backend=cpu)"
    ) from exc

from .config import HerculeLMConfig

EPS = 1e-5
IGNORE_ID = -100
ORIGIN = "hercule-lm random initialization (no pretrained weights)"

# NumPy name -> (kind, layer_index or None, torch_attr)
_TORCH_ATTRS = ("tokE", "posE", "lnfW", "lnfb", "headW", "headb")
_BLOCK_ATTRS = ("ln1W", "ln1b", "qkvW", "qkvb", "oW", "ob",
                "ln2W", "ln2b", "f1W", "f1b", "f2W", "f2b")


def numpy_name(layer: int, attr: str) -> str:
    return f"L{layer}.{attr}"


def all_numpy_names(config: HerculeLMConfig) -> list:
    names = ["tokE", "posE"]
    for layer in range(config.num_layers):
        names.extend(numpy_name(layer, a) for a in _BLOCK_ATTRS)
    names.extend(["lnfW", "lnfb", "headW", "headb"])
    return names


def random_init_dict(config: HerculeLMConfig, seed: int) -> dict:
    """Bit-identical initial values to ``HerculeLM._init_weights``.

    Uses the same ``numpy.random.default_rng(seed)`` draw order so a
    torch model and a NumPy model with the same seed start from the
    same point (float32). Random only — no pretrained data anywhere.
    """
    config.validate()
    rng = np.random.default_rng(int(seed))
    d, v, c = config.hidden_size, config.vocab_size, config.context_length

    def xavier(*shape):
        fan_in, fan_out = shape[-2], shape[-1]
        limit = float(np.sqrt(6.0 / (fan_in + fan_out)))
        return rng.uniform(-limit, limit, size=shape).astype(np.float32)

    def normal(*shape, std: float = 0.02):
        return (rng.standard_normal(shape).astype(np.float32) * std)

    init_fn = xavier if config.initialization == "xavier-uniform" else normal

    params: dict = {}
    params["tokE"] = normal(v, d, std=0.02)

    # Positional embeddings only for learned positional
    if config.positional == "learned":
        params["posE"] = normal(c, d, std=0.02)
    else:
        params["posE"] = np.zeros((c, d), dtype=np.float32)  # unused

    for layer in range(config.num_layers):
        p = f"L{layer}."
        # Norm 1
        if config.normalization == "layernorm":
            params[p + "ln1W"] = np.ones(d, dtype=np.float32)
            params[p + "ln1b"] = np.zeros(d, dtype=np.float32)
        else:  # rmsnorm - no bias
            params[p + "ln1W"] = np.ones(d, dtype=np.float32)
            params[p + "ln1b"] = np.zeros(d, dtype=np.float32)  # unused

        # QKV projection
        params[p + "qkvW"] = init_fn(d, 3 * d)
        if config.qkv_bias:
            params[p + "qkvb"] = np.zeros(3 * d, dtype=np.float32)
        else:
            params[p + "qkvb"] = np.zeros(3 * d, dtype=np.float32)  # unused

        # Attention output
        params[p + "oW"] = init_fn(d, d)
        if config.out_bias:
            params[p + "ob"] = np.zeros(d, dtype=np.float32)
        else:
            params[p + "ob"] = np.zeros(d, dtype=np.float32)  # unused

        # Norm 2
        if config.normalization == "layernorm":
            params[p + "ln2W"] = np.ones(d, dtype=np.float32)
            params[p + "ln2b"] = np.zeros(d, dtype=np.float32)
        else:  # rmsnorm - no bias
            params[p + "ln2W"] = np.ones(d, dtype=np.float32)
            params[p + "ln2b"] = np.zeros(d, dtype=np.float32)  # unused

        # FFN
        ffn_hidden = config.ffn_size
        if config.activation == "geglu":
            ffn_hidden = config.ffn_size * 2
        params[p + "f1W"] = init_fn(d, ffn_hidden)
        if config.ffn_bias:
            params[p + "f1b"] = np.zeros(ffn_hidden, dtype=np.float32)
        else:
            params[p + "f1b"] = np.zeros(ffn_hidden, dtype=np.float32)  # unused
        params[p + "f2W"] = init_fn(config.ffn_size, d)
        if config.ffn_bias:
            params[p + "f2b"] = np.zeros(d, dtype=np.float32)
        else:
            params[p + "f2b"] = np.zeros(d, dtype=np.float32)  # unused

    # Final norm
    if config.normalization == "layernorm":
        params["lnfW"] = np.ones(d, dtype=np.float32)
        params["lnfb"] = np.zeros(d, dtype=np.float32)
    else:  # rmsnorm - no bias
        params["lnfW"] = np.ones(d, dtype=np.float32)
        params["lnfb"] = np.zeros(d, dtype=np.float32)  # unused

    # Output head
    if not config.tied_embeddings:
        params["headW"] = init_fn(d, v)
        if config.out_bias:
            params["headb"] = np.zeros(v, dtype=np.float32)
        else:
            params["headb"] = np.zeros(v, dtype=np.float32)  # unused
    else:
        params["headW"] = np.zeros((d, v), dtype=np.float32)  # unused
        params["headb"] = np.zeros(v, dtype=np.float32)  # unused

    return params


class _TorchBlock(nn.Module):
    def __init__(self, init: dict, layer: int, config: HerculeLMConfig):
        super().__init__()
        self.config = config
        # Always register these
        for attr in ("ln1W", "qkvW", "oW", "ln2W", "f1W", "f2W"):
            arr = np.asarray(init[numpy_name(layer, attr)], dtype=np.float32)
            self.register_parameter(attr, nn.Parameter(torch.from_numpy(arr.copy())))
        # Conditionally register bias parameters
        if config.normalization == "layernorm":
            for attr in ("ln1b", "ln2b"):
                arr = np.asarray(init[numpy_name(layer, attr)], dtype=np.float32)
                self.register_parameter(attr, nn.Parameter(torch.from_numpy(arr.copy())))
        else:
            # Register as buffers (not parameters) for RMSNorm
            for attr in ("ln1b", "ln2b"):
                arr = np.asarray(init[numpy_name(layer, attr)], dtype=np.float32)
                self.register_buffer(attr, torch.from_numpy(arr.copy()), persistent=False)
        if config.qkv_bias:
            arr = np.asarray(init[numpy_name(layer, "qkvb")], dtype=np.float32)
            self.register_parameter("qkvb", nn.Parameter(torch.from_numpy(arr.copy())))
        else:
            arr = np.asarray(init[numpy_name(layer, "qkvb")], dtype=np.float32)
            self.register_buffer("qkvb", torch.from_numpy(arr.copy()), persistent=False)
        if config.out_bias:
            arr = np.asarray(init[numpy_name(layer, "ob")], dtype=np.float32)
            self.register_parameter("ob", nn.Parameter(torch.from_numpy(arr.copy())))
        else:
            arr = np.asarray(init[numpy_name(layer, "ob")], dtype=np.float32)
            self.register_buffer("ob", torch.from_numpy(arr.copy()), persistent=False)
        if config.ffn_bias:
            arr = np.asarray(init[numpy_name(layer, "f1b")], dtype=np.float32)
            self.register_parameter("f1b", nn.Parameter(torch.from_numpy(arr.copy())))
            arr = np.asarray(init[numpy_name(layer, "f2b")], dtype=np.float32)
            self.register_parameter("f2b", nn.Parameter(torch.from_numpy(arr.copy())))
        else:
            arr = np.asarray(init[numpy_name(layer, "f1b")], dtype=np.float32)
            self.register_buffer("f1b", torch.from_numpy(arr.copy()), persistent=False)
            arr = np.asarray(init[numpy_name(layer, "f2b")], dtype=np.float32)
            self.register_buffer("f2b", torch.from_numpy(arr.copy()), persistent=False)


def _layernorm(x: torch.Tensor, weight: torch.Tensor, bias: torch.Tensor, eps: float = EPS) -> torch.Tensor:
    mean = x.mean(dim=-1, keepdim=True)
    var = ((x - mean) ** 2).mean(dim=-1, keepdim=True)
    xhat = (x - mean) / torch.sqrt(var + eps)
    return weight * xhat + bias


def _rmsnorm(x: torch.Tensor, weight: torch.Tensor, eps: float = EPS) -> torch.Tensor:
    rms = torch.sqrt((x * x).mean(dim=-1, keepdim=True) + eps)
    return weight * (x / rms)


def _gelu(x: torch.Tensor) -> torch.Tensor:
    c = math.sqrt(2.0 / math.pi)
    return 0.5 * x * (1.0 + torch.tanh(c * (x + 0.044715 * x ** 3)))


def _silu(x: torch.Tensor) -> torch.Tensor:
    return x * torch.sigmoid(x)


def _geglu(x: torch.Tensor) -> torch.Tensor:
    gate, value = x.chunk(2, dim=-1)
    return _gelu(gate) * value


def _act_fn(config: HerculeLMConfig):
    if config.activation == "gelu":
        return _gelu
    elif config.activation == "silu":
        return _silu
    elif config.activation == "geglu":
        return _geglu
    else:
        raise ValueError(f"unknown activation: {config.activation}")


def _norm_fn(config: HerculeLMConfig):
    if config.normalization == "layernorm":
        return lambda x, w, b: _layernorm(x, w, b, config.norm_eps)
    else:
        return lambda x, w, b: _rmsnorm(x, w, config.norm_eps)


def _rope_cache(seq_len: int, head_dim: int, theta: float = 10000.0, device=None, dtype=torch.float32):
    """Precompute RoPE cos/sin cache."""
    assert head_dim % 2 == 0, "head_dim must be even for RoPE"
    pos = torch.arange(seq_len, device=device, dtype=dtype)[:, None]
    dim_idx = torch.arange(0, head_dim, 2, device=device, dtype=dtype)[None, :]
    freqs = 1.0 / (theta ** (dim_idx / head_dim))
    angles = pos * freqs
    cos = torch.cos(angles).to(dtype)
    sin = torch.sin(angles).to(dtype)
    return cos, sin


def _apply_rope(q: torch.Tensor, k: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> tuple:
    """Apply RoPE to q and k. Shapes: (B, H, T, dh) where dh is even."""
    B, H, T, dh = q.shape
    assert dh % 2 == 0
    half = dh // 2
    q_real = q[..., :half]
    q_imag = q[..., half:]
    k_real = k[..., :half]
    k_imag = k[..., half:]
    cos = cos[:T].reshape(1, 1, T, half)
    sin = sin[:T].reshape(1, 1, T, half)
    q_rot_real = q_real * cos - q_imag * sin
    q_rot_imag = q_real * sin + q_imag * cos
    k_rot_real = k_real * cos - k_imag * sin
    k_rot_imag = k_real * sin + k_imag * cos
    q_out = torch.cat([q_rot_real, q_rot_imag], dim=-1)
    k_out = torch.cat([k_rot_real, k_rot_imag], dim=-1)
    return q_out, k_out


class TorchHerculeLM(nn.Module):
    """Randomly-initialized causal LM on torch (real autograd)."""

    def __init__(self, config: HerculeLMConfig, seed: int = 0):
        super().__init__()
        config.validate()
        self.config = config
        self.seed = int(seed)
        init = random_init_dict(config, self.seed)
        self.tokE = nn.Parameter(torch.from_numpy(init["tokE"].copy()))
        if config.positional == "learned":
            self.posE = nn.Parameter(torch.from_numpy(init["posE"].copy()))
        else:
            self.register_buffer("posE", torch.from_numpy(init["posE"].copy()), persistent=False)
        self.blocks = nn.ModuleList(
            _TorchBlock(init, layer, config) for layer in range(config.num_layers))
        self.lnfW = nn.Parameter(torch.from_numpy(init["lnfW"].copy()))
        if config.normalization == "layernorm":
            self.lnfb = nn.Parameter(torch.from_numpy(init["lnfb"].copy()))
        else:
            self.register_buffer("lnfb", torch.from_numpy(init["lnfb"].copy()), persistent=False)
        if not config.tied_embeddings:
            self.headW = nn.Parameter(torch.from_numpy(init["headW"].copy()))
            self.headb = nn.Parameter(torch.from_numpy(init["headb"].copy()))
        else:
            self.register_buffer("headW", torch.empty(0), persistent=False)
            self.register_buffer("headb", torch.empty(0), persistent=False)
        self._step_count = 0

        # Precompute RoPE cache
        if config.positional == "rope":
            dh = config.hidden_size // config.num_heads
            cos, sin = _rope_cache(config.context_length, dh, config.rope_theta)
            self.register_buffer("_rope_cos", cos, persistent=False)
            self.register_buffer("_rope_sin", sin, persistent=False)
        else:
            self.register_buffer("_rope_cos", torch.empty(0), persistent=False)
            self.register_buffer("_rope_sin", torch.empty(0), persistent=False)

        # ALiBi slopes
        if config.positional == "alibi":
            slopes = self._compute_alibi_slopes(config.num_heads)
            self.register_buffer("_alibi_slopes", slopes, persistent=False)
        else:
            self.register_buffer("_alibi_slopes", torch.empty(0), persistent=False)

    @property
    def device(self) -> torch.device:
        return self.tokE.device

    def parameter_count(self) -> int:
        return int(sum(p.numel() for p in self.parameters()))

    def _compute_alibi_slopes(self, num_heads: int) -> torch.Tensor:
        start = 2 ** (-(8 / num_heads))
        ratio = start
        slopes = torch.tensor([start * (ratio ** i) for i in range(num_heads)], dtype=torch.float32)
        return slopes

    def numpy_param_dict(self) -> dict:
        """Detached CPU float32 copies keyed by NumPy parameter names."""
        out = {
            "tokE": self.tokE.detach().cpu().numpy().astype(np.float32),
            "posE": self.posE.detach().cpu().numpy().astype(np.float32),
        }
        for i, block in enumerate(self.blocks):
            for attr in _BLOCK_ATTRS:
                out[numpy_name(i, attr)] = (
                    getattr(block, attr).detach().cpu().numpy().astype(np.float32))
        out["lnfW"] = self.lnfW.detach().cpu().numpy().astype(np.float32)
        out["lnfb"] = self.lnfb.detach().cpu().numpy().astype(np.float32)
        out["headW"] = self.headW.detach().cpu().numpy().astype(np.float32)
        out["headb"] = self.headb.detach().cpu().numpy().astype(np.float32)
        return out

    def load_numpy_param_dict(self, params: dict, strict: bool = True) -> None:
        """Load NumPy-keyed arrays into torch parameters (explicit conversion)."""
        with torch.no_grad():
            for key in all_numpy_names(self.config):
                if key not in params:
                    if strict:
                        raise ValueError(f"CHECKPOINT_CORRUPTED: missing param {key}")
                    continue
                arr = np.asarray(params[key], dtype=np.float32)
                if key in _TORCH_ATTRS:
                    getattr(self, key).data.copy_(torch.from_numpy(arr).to(getattr(self, key).device))
                else:
                    layer_s, attr = key.split(".", 1)
                    target = getattr(self.blocks[int(layer_s[1:])], attr)
                    target.data.copy_(torch.from_numpy(arr).to(target.device))

    # --------------------------------------------------
    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        """Logits ``(B, T, V)``. ``ids``: long tensor on the model device."""
        cfg = self.config
        B, T = ids.shape
        dh = cfg.hidden_size // cfg.num_heads

        x = F.embedding(ids, self.tokE)
        if cfg.positional == "learned":
            x = x + self.posE[:T].unsqueeze(0)

        act_fn = _act_fn(cfg)
        norm_fn = _norm_fn(cfg)

        for block in self.blocks:
            # Norm 1
            if cfg.normalization == "layernorm":
                h = norm_fn(x, block.ln1W, block.ln1b)
            else:
                h = norm_fn(x, block.ln1W, block.ln1b)  # bias ignored in rmsnorm

            # QKV projection
            qkv = h @ block.qkvW
            if cfg.qkv_bias:
                qkv = qkv + block.qkvb
            heads = qkv.reshape(B, T, cfg.num_heads, 3 * dh)
            q = heads[:, :, :, :dh].transpose(1, 2)
            k = heads[:, :, :, dh:2 * dh].transpose(1, 2)
            v = heads[:, :, :, 2 * dh:].transpose(1, 2)

            # RoPE
            if cfg.positional == "rope":
                q, k = _apply_rope(q, k, self._rope_cos, self._rope_sin)

            scores = q @ k.transpose(-2, -1) / math.sqrt(dh)

            # ALiBi
            if cfg.positional == "alibi":
                alibi_bias = self._alibi_slopes[None, :, None, None] * torch.arange(T, device=ids.device)[None, None, :, None]
                alibi_bias = alibi_bias - alibi_bias.transpose(-2, -1)
                scores = scores + alibi_bias

            # Causal mask (mask value must fit the scores dtype:
            # -1e9 overflows fp16, whose max is ~65504)
            mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=ids.device), diagonal=1)
            mask_value = -1e4 if scores.dtype == torch.float16 else -1e9
            scores = scores.masked_fill(mask.unsqueeze(0).unsqueeze(0), mask_value)

            probs = torch.softmax(scores, dim=-1)
            ctx = (probs @ v).transpose(1, 2).reshape(B, T, cfg.hidden_size)

            # Attention output
            attn_out = ctx @ block.oW
            if cfg.out_bias:
                attn_out = attn_out + block.ob
            x = x + attn_out

            # Norm 2
            if cfg.normalization == "layernorm":
                h2 = norm_fn(x, block.ln2W, block.ln2b)
            else:
                h2 = norm_fn(x, block.ln2W, block.ln2b)

            # FFN
            f1 = h2 @ block.f1W
            if cfg.ffn_bias:
                f1 = f1 + block.f1b
            g = act_fn(f1)
            f2 = g @ block.f2W
            if cfg.ffn_bias:
                f2 = f2 + block.f2b
            x = x + f2

        # Final norm
        if cfg.normalization == "layernorm":
            hfin = norm_fn(x, self.lnfW, self.lnfb)
        else:
            hfin = norm_fn(x, self.lnfW, self.lnfb)

        # Output projection (tied or untied)
        if cfg.tied_embeddings:
            logits = hfin @ self.tokE.T
        else:
            logits = hfin @ self.headW
            if cfg.out_bias:
                logits = logits + self.headb
        return logits

    def cross_entropy(self, logits: torch.Tensor, targets: torch.Tensor,
                      ignore_id: int = IGNORE_ID) -> torch.Tensor:
        """Mean cross-entropy over non-ignored positions (scalar tensor)."""
        flat_logits = logits.reshape(-1, logits.shape[-1])
        flat_targets = targets.reshape(-1)
        keep = flat_targets != ignore_id
        if not bool(keep.any()):
            return logits.sum() * 0.0
        kept_logits = flat_logits[keep]
        kept_targets = flat_targets[keep]
        log_probs = torch.log_softmax(kept_logits, dim=-1)
        return torch.nn.functional.nll_loss(log_probs, kept_targets, reduction="mean")

    # --------------------------------------------------
    def forward_step(self, token: torch.Tensor, pos: int,
                     past: list | None = None) -> tuple:
        """Single-position forward with KV cache. ``token``: (B,1) long.

        Returns (logits (B,1,V), new_past). past entries are (k, v) with
        shape (B,H,T,dh); causal order is structural (query is newest),
        so no mask is needed. Mathematically identical to forward().
        """
        cfg = self.config
        dh = cfg.hidden_size // cfg.num_heads
        past = list(past) if past else [None] * len(self.blocks)
        x = F.embedding(token, self.tokE)
        if cfg.positional == "learned":
            x = x + self.posE[pos].unsqueeze(0).unsqueeze(0)

        act_fn = _act_fn(cfg)
        norm_fn = _norm_fn(cfg)
        new_past: list = []

        for i, block in enumerate(self.blocks):
            if cfg.normalization == "layernorm":
                h = norm_fn(x, block.ln1W, block.ln1b)
            else:
                h = norm_fn(x, block.ln1W, block.ln1b)
            qkv = h @ block.qkvW
            if cfg.qkv_bias:
                qkv = qkv + block.qkvb
            heads = qkv.reshape(token.shape[0], 1, cfg.num_heads, 3 * dh)
            q = heads[:, :, :, :dh].transpose(1, 2)
            k = heads[:, :, :, dh:2 * dh].transpose(1, 2)
            v = heads[:, :, :, 2 * dh:].transpose(1, 2)

            if cfg.positional == "rope":
                q, k = _apply_rope(q, k, self._rope_cos, self._rope_sin)

            if past[i] is not None:
                pk, pv = past[i]
                k = torch.cat([pk, k], dim=2)
                v = torch.cat([pv, v], dim=2)
            new_past.append((k, v))

            # No causal mask needed with KV cache (causal by construction)
            probs = torch.softmax(q @ k.transpose(-2, -1) / math.sqrt(dh), dim=-1)
            ctx = (probs @ v).transpose(1, 2).reshape(token.shape[0], 1, cfg.hidden_size)

            attn_out = ctx @ block.oW
            if cfg.out_bias:
                attn_out = attn_out + block.ob
            x = x + attn_out

            if cfg.normalization == "layernorm":
                h2 = norm_fn(x, block.ln2W, block.ln2b)
            else:
                h2 = norm_fn(x, block.ln2W, block.ln2b)

            f1 = h2 @ block.f1W
            if cfg.ffn_bias:
                f1 = f1 + block.f1b
            x = x + (act_fn(f1) @ block.f2W + (block.f2b if cfg.ffn_bias else 0))

        if cfg.normalization == "layernorm":
            hfin = norm_fn(x, self.lnfW, self.lnfb)
        else:
            hfin = norm_fn(x, self.lnfW, self.lnfb)

        if cfg.tied_embeddings:
            logits = hfin @ self.tokE.T
        else:
            logits = hfin @ self.headW
            if cfg.out_bias:
                logits = logits + self.headb
        return logits, new_past

    @torch.no_grad()
    def generate_cached(self, start_ids: list, max_new_tokens: int = 32,
                        temperature: float = 0.0, seed: int = 0) -> list:
        """Greedy/sampled generation with KV cache (streaming-ready)."""
        gen = torch.Generator(device="cpu").manual_seed(int(seed))
        ids = list(int(i) for i in start_ids)
        ctx = int(self.config.context_length)
        was_training = self.training
        self.eval()
        try:
            past: list | None = None
            window = ids[-ctx:]
            for pos, tok in enumerate(window):
                t = torch.tensor([[tok]], dtype=torch.long, device=self.device)
                logits, past = self.forward_step(t, pos, past)
            for _ in range(max_new_tokens):
                next_logits = logits[0, -1].double().cpu()
                if temperature <= 0:
                    nxt = int(torch.argmax(next_logits).item())
                else:
                    probs = torch.softmax(next_logits / max(1e-6, temperature), dim=-1)
                    nxt = int(torch.multinomial(probs, 1, generator=gen).item())
                ids.append(nxt)
                if nxt == 2 or len(ids) >= ctx + max_new_tokens:
                    break
                t = torch.tensor([[nxt]], dtype=torch.long, device=self.device)
                logits, past = self.forward_step(
                    t, min(len(ids) - 1, ctx - 1), past)
                if len(past[0][0][0, 0]) >= ctx:
                    past = [(k[:, :, 1:, :], v[:, :, 1:, :]) for k, v in past]
        finally:
            if was_training:
                self.train()
        return ids

    def stream_generate(self, start_ids: list, max_new_tokens: int = 32,
                          temperature: float = 0.0, seed: int = 0):
        """Yield tokens incrementally (streaming-ready, KV-cached)."""
        gen = torch.Generator(device="cpu").manual_seed(int(seed))
        ids = list(int(i) for i in start_ids)
        ctx = int(self.config.context_length)
        was_training = self.training
        self.eval()
        try:
            with torch.no_grad():
                past: list | None = None
                window = ids[-ctx:]
                for pos, tok in enumerate(window):
                    t = torch.tensor([[tok]], dtype=torch.long, device=self.device)
                    logits, past = self.forward_step(t, pos, past)
                for step in range(max_new_tokens):
                    next_logits = logits[0, -1].double().cpu()
                    if temperature <= 0:
                        nxt = int(torch.argmax(next_logits).item())
                    else:
                        probs = torch.softmax(next_logits / max(1e-6, temperature), dim=-1)
                        nxt = int(torch.multinomial(probs, 1, generator=gen).item())
                    ids.append(nxt)
                    done = nxt == 2 or step == max_new_tokens - 1
                    yield {"token": nxt, "index": len(ids) - 1, "done": done}
                    if done:
                        break
                    t = torch.tensor([[nxt]], dtype=torch.long, device=self.device)
                    logits, past = self.forward_step(
                        t, min(len(ids) - 1, ctx - 1), past)
                    if len(past[0][0][0, 0]) >= ctx:
                        past = [(k[:, :, 1:, :], v[:, :, 1:, :]) for k, v in past]
        finally:
            if was_training:
                self.train()

    @torch.no_grad()
    def generate(self, start_ids: list, max_new_tokens: int = 32,
                 temperature: float = 0.0, seed: int = 0) -> list:
        """Greedy (temperature<=0) continuation; deterministic given seed."""
        gen = torch.Generator(device="cpu").manual_seed(int(seed))
        ids = list(int(i) for i in start_ids)
        ctx = int(self.config.context_length)
        was_training = self.training
        self.eval()
        try:
            for _ in range(max_new_tokens):
                window = torch.tensor([ids[-ctx:]], dtype=torch.long, device=self.device)
                next_logits = self.forward(window)[0, -1].double().cpu()
                if temperature <= 0:
                    nxt = int(torch.argmax(next_logits).item())
                else:
                    probs = torch.softmax(next_logits / max(1e-6, temperature), dim=-1)
                    nxt = int(torch.multinomial(probs, 1, generator=gen).item())
                ids.append(nxt)
                if nxt == 2:  # EOS
                    break
        finally:
            if was_training:
                self.train()
        return ids