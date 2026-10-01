from __future__ import annotations
"""HERCULE-LM causal transformer (N9): own NumPy implementation.

Decoder-only: token + positional embeddings (learned/RoPE/ALiBi), N blocks of
(Norm → causal multi-head self-attention → residual →
Norm → Activation FFN → residual), final norm + output head,
cross-entropy loss. Forward AND backward are hand-written; no
autograd library, no pretrained weights. Configurable initialization.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from .config import HerculeLMConfig

EPS = 1e-5


@dataclass
class KVCache:
    """Key-Value cache for attention layers."""
    layers: List[Dict[str, np.ndarray]] = field(default_factory=list)
    seq_len: int = 0
    batch_size: int = 0
    max_seq_len: int = 0
    
    def __init__(self, num_layers: int, batch_size: int, max_seq_len: int, hidden_size: int, num_heads: int, head_dim: int):
        self.layers = []
        self.seq_len = 0
        self.batch_size = batch_size
        self.max_seq_len = max_seq_len
        for _ in range(num_layers):
            self.layers.append({
                "k": np.zeros((batch_size, num_heads, max_seq_len, head_dim), dtype=np.float32),
                "v": np.zeros((batch_size, num_heads, max_seq_len, head_dim), dtype=np.float32),
            })
    
    def update(self, layer_idx: int, k: np.ndarray, v: np.ndarray, pos: int):
        """Update cache at position."""
        layer = self.layers[layer_idx]
        layer["k"][:, :, pos:pos+k.shape[2]] = k
        layer["v"][:, :, pos:pos+v.shape[2]] = v
    
    def get(self, layer_idx: int, pos: int) -> Tuple[np.ndarray, np.ndarray]:
        """Get cached K,V up to position."""
        layer = self.layers[layer_idx]
        return layer["k"][:, :, :pos], layer["v"][:, :, :pos]
    
    def reset(self):
        """Reset cache for new sequence."""
        self.seq_len = 0
        for layer in self.layers:
            layer["k"].fill(0)
            layer["v"].fill(0)


def _softmax(x: np.ndarray) -> np.ndarray:
    shifted = x - x.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


def _gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x ** 3)))


def _gelu_backward(dout: np.ndarray, x: np.ndarray) -> np.ndarray:
    c = np.sqrt(2.0 / np.pi)
    inner = c * (x + 0.044715 * x ** 3)
    tanh_inner = np.tanh(inner)
    d_inner = c * (1.0 + 3.0 * 0.044715 * x ** 2)
    return dout * (0.5 * (1.0 + tanh_inner) + 0.5 * x * (1.0 - tanh_inner ** 2) * d_inner)


def _silu(x: np.ndarray) -> np.ndarray:
    return x / (1.0 + np.exp(-x))


def _silu_backward(dout: np.ndarray, x: np.ndarray) -> np.ndarray:
    sigmoid = 1.0 / (1.0 + np.exp(-x))
    return dout * (sigmoid + x * sigmoid * (1.0 - sigmoid))


def _geglu(x: np.ndarray) -> np.ndarray:
    # x shape: (..., 2*hidden) -> split into gate and value
    gate, value = np.split(x, 2, axis=-1)
    return _gelu(gate) * value


def _geglu_backward(dout: np.ndarray, x: np.ndarray) -> np.ndarray:
    gate, value = np.split(x, 2, axis=-1)
    c = np.sqrt(2.0 / np.pi)
    inner = c * (gate + 0.044715 * gate ** 3)
    tanh_inner = np.tanh(inner)
    d_inner = c * (1.0 + 3.0 * 0.044715 * gate ** 2)
    gelu_gate = 0.5 * (1.0 + tanh_inner)
    d_gelu_gate = 0.5 * (1.0 - tanh_inner ** 2) * d_inner
    d_gate = dout * value * d_gelu_gate
    d_value = dout * gelu_gate
    return np.concatenate([d_gate, d_value], axis=-1)


def _layernorm_forward(x: np.ndarray, gamma: np.ndarray, beta: np.ndarray, eps: float = EPS):
    mean = x.mean(axis=-1, keepdims=True)
    var = ((x - mean) ** 2).mean(axis=-1, keepdims=True)
    xhat = (x - mean) / np.sqrt(var + eps)
    return gamma * xhat + beta, (x, xhat, mean, var, gamma, eps)


def _layernorm_backward(dout: np.ndarray, cache) -> tuple:
    x, xhat, mean, var, gamma, eps = cache
    d = x.shape[-1]
    dxhat = dout * gamma
    dvar = (dxhat * (x - mean) * -0.5 * (var + eps) ** (-1.5)).sum(axis=-1, keepdims=True)
    dmean = (dxhat * -1.0 / np.sqrt(var + eps)).sum(axis=-1, keepdims=True) + \
        dvar * ((x - mean) * -2.0).mean(axis=-1, keepdims=True)
    dx = dxhat / np.sqrt(var + eps) + dvar * 2.0 * (x - mean) / d + dmean / d
    dgamma = (dout * xhat).sum(axis=tuple(range(dout.ndim - 1)))
    dbeta = dout.sum(axis=tuple(range(dout.ndim - 1)))
    return dx, dgamma, dbeta


def _rmsnorm_forward(x: np.ndarray, gamma: np.ndarray, eps: float = EPS):
    # RMSNorm: x * gamma / sqrt(mean(x^2) + eps)  (no beta, no mean subtraction)
    rms = np.sqrt((x * x).mean(axis=-1, keepdims=True) + eps)
    xhat = x / rms
    return gamma * xhat, (x, xhat, rms, gamma, eps)


def _rmsnorm_backward(dout: np.ndarray, cache) -> tuple:
    x, xhat, rms, gamma, eps = cache
    d = x.shape[-1]
    dxhat = dout * gamma
    # drms = sum(dxhat * xhat * -1/rms) but xhat = x/rms
    # drms = -sum(dxhat * x) / rms^2
    drms = -(dxhat * x).sum(axis=-1, keepdims=True) / (rms * rms)
    dx = dxhat / rms + drms * x / (d * rms)
    dgamma = (dout * xhat).sum(axis=tuple(range(dout.ndim - 1)))
    return dx, dgamma, np.zeros_like(gamma)  # no beta in RMSNorm


def _rope_cache(seq_len: int, head_dim: int, theta: float = 10000.0, dtype=np.float32):
    """Precompute RoPE cos/sin cache."""
    assert head_dim % 2 == 0, "head_dim must be even for RoPE"
    pos = np.arange(seq_len, dtype=dtype)[:, None]  # (seq_len, 1)
    dim_idx = np.arange(0, head_dim, 2, dtype=dtype)[None, :]  # (1, head_dim/2)
    freqs = 1.0 / (theta ** (dim_idx / head_dim))  # (1, head_dim/2)
    angles = pos * freqs  # (seq_len, head_dim/2)
    cos = np.cos(angles).astype(dtype)
    sin = np.sin(angles).astype(dtype)
    return cos, sin


def _apply_rope(q: np.ndarray, k: np.ndarray, cos: np.ndarray, sin: np.ndarray) -> tuple:
    """Apply RoPE to q and k. Shapes: (B, H, T, dh) where dh is even."""
    B, H, T, dh = q.shape
    assert dh % 2 == 0
    half = dh // 2
    # Split real/imag parts
    q_real = q[..., :half]
    q_imag = q[..., half:]
    k_real = k[..., :half]
    k_imag = k[..., half:]
    # cos/sin: (T, half) -> broadcast to (1, 1, T, half)
    cos = cos[:T].reshape(1, 1, T, half)
    sin = sin[:T].reshape(1, 1, T, half)
    # Rotate: [x, y] -> [x*cos - y*sin, x*sin + y*cos]
    q_rot_real = q_real * cos - q_imag * sin
    q_rot_imag = q_real * sin + q_imag * cos
    k_rot_real = k_real * cos - k_imag * sin
    k_rot_imag = k_real * sin + k_imag * cos
    # Concatenate back
    q_out = np.concatenate([q_rot_real, q_rot_imag], axis=-1)
    k_out = np.concatenate([k_rot_real, k_rot_imag], axis=-1)
    return q_out, k_out


def _apply_rope_single(x: np.ndarray, cos: np.ndarray, sin: np.ndarray, pos_offset: int = 0) -> np.ndarray:
    """Apply RoPE to a single tensor with position offset.
    
    Args:
        x: (B, H, T, dh) where dh is even
        cos: precomputed cos cache (max_seq_len, half)
        sin: precomputed sin cache (max_seq_len, half)
        pos_offset: starting position index for the first token in x
    """
    B, H, T, dh = x.shape
    assert dh % 2 == 0
    half = dh // 2
    # Split real/imag parts
    x_real = x[..., :half]
    x_imag = x[..., half:]
    # cos/sin for positions pos_offset to pos_offset + T - 1
    cos = cos[pos_offset:pos_offset + T].reshape(1, 1, T, half)
    sin = sin[pos_offset:pos_offset + T].reshape(1, 1, T, half)
    # Rotate: [x, y] -> [x*cos - y*sin, x*sin + y*cos]
    x_rot_real = x_real * cos - x_imag * sin
    x_rot_imag = x_real * sin + x_imag * cos
    # Concatenate back
    return np.concatenate([x_rot_real, x_rot_imag], axis=-1)


class HerculeLM:
    """Randomly-initialized causal LM. Owns weights, optimizer, step."""

    def __init__(self, config: HerculeLMConfig, seed: int = 0):
        config.validate()
        self.config = config
        self.seed = int(seed)
        self.params: dict = {}
        self._rope_cos: np.ndarray = None
        self._rope_sin: np.ndarray = None
        self._init_weights()
        self.opt_state: dict = {}
        self._step_count = 0

    # --------------------------------------------------
    def _init_weights(self) -> None:
        rng = np.random.default_rng(self.seed)
        cfg = self.config
        d, v, c = cfg.hidden_size, cfg.vocab_size, cfg.context_length

        def xavier(*shape):
            fan_in, fan_out = shape[-2], shape[-1]
            limit = float(np.sqrt(6.0 / (fan_in + fan_out)))
            return rng.uniform(-limit, limit, size=shape).astype(np.float32)

        def normal(*shape, std: float = 0.02):
            return (rng.standard_normal(shape).astype(np.float32) * std)

        init_fn = xavier if cfg.initialization == "xavier-uniform" else normal

        # Token embeddings
        self.params["tokE"] = normal(v, d, std=0.02)

        # Positional embeddings (only for learned positional)
        if cfg.positional == "learned":
            self.params["posE"] = normal(c, d, std=0.02)

        # RoPE cache (precomputed, not learned)
        if cfg.positional == "rope":
            dh = d // cfg.num_heads
            self._rope_cos, self._rope_sin = _rope_cache(c, dh, cfg.rope_theta)

        for layer in range(cfg.num_layers):
            p = f"L{layer}."
            # Norm 1
            if cfg.normalization == "layernorm":
                self.params[p + "ln1W"] = np.ones(d, dtype=np.float32)
                self.params[p + "ln1b"] = np.zeros(d, dtype=np.float32)
            else:  # rmsnorm
                self.params[p + "ln1W"] = np.ones(d, dtype=np.float32)
                # No bias for RMSNorm

            # QKV projection
            self.params[p + "qkvW"] = init_fn(d, 3 * d)
            if cfg.qkv_bias:
                self.params[p + "qkvb"] = np.zeros(3 * d, dtype=np.float32)

            # Attention output
            self.params[p + "oW"] = init_fn(d, d)
            if cfg.out_bias:
                self.params[p + "ob"] = np.zeros(d, dtype=np.float32)

            # Norm 2
            if cfg.normalization == "layernorm":
                self.params[p + "ln2W"] = np.ones(d, dtype=np.float32)
                self.params[p + "ln2b"] = np.zeros(d, dtype=np.float32)
            else:  # rmsnorm
                self.params[p + "ln2W"] = np.ones(d, dtype=np.float32)

            # FFN
            ffn_hidden = cfg.ffn_size
            if cfg.activation == "geglu":
                # GeGLU needs 2*ffn_size for gate+value
                ffn_hidden = cfg.ffn_size * 2
            self.params[p + "f1W"] = init_fn(d, ffn_hidden)
            if cfg.ffn_bias:
                self.params[p + "f1b"] = np.zeros(ffn_hidden, dtype=np.float32)
            self.params[p + "f2W"] = init_fn(cfg.ffn_size, d)
            if cfg.ffn_bias:
                self.params[p + "f2b"] = np.zeros(d, dtype=np.float32)

        # Final norm
        if cfg.normalization == "layernorm":
            self.params["lnfW"] = np.ones(d, dtype=np.float32)
            self.params["lnfb"] = np.zeros(d, dtype=np.float32)
        else:  # rmsnorm
            self.params["lnfW"] = np.ones(d, dtype=np.float32)

        # Output head
        if not cfg.tied_embeddings:
            self.params["headW"] = init_fn(d, v)
            if cfg.out_bias:
                self.params["headb"] = np.zeros(v, dtype=np.float32)

        # Precompute RoPE cache if needed
        if cfg.positional == "rope" and self._rope_cos is None:
            dh = d // cfg.num_heads
            self._rope_cos, self._rope_sin = _rope_cache(c, dh, cfg.rope_theta)

    def parameter_count(self) -> int:
        return int(sum(p.size for p in self.params.values()))

    # --------------------------------------------------
    def _norm_forward(self, x: np.ndarray, gamma: np.ndarray, beta: np.ndarray = None):
        cfg = self.config
        if cfg.normalization == "layernorm":
            return _layernorm_forward(x, gamma, beta, cfg.norm_eps)
        else:
            return _rmsnorm_forward(x, gamma, cfg.norm_eps)

    def _norm_backward(self, dout: np.ndarray, cache):
        cfg = self.config
        if cfg.normalization == "layernorm":
            return _layernorm_backward(dout, cache)
        else:
            return _rmsnorm_backward(dout, cache)

    def _act_forward(self, x: np.ndarray) -> np.ndarray:
        cfg = self.config
        if cfg.activation == "gelu":
            return _gelu(x)
        elif cfg.activation == "silu":
            return _silu(x)
        elif cfg.activation == "geglu":
            return _geglu(x)
        else:
            raise ValueError(f"unknown activation: {cfg.activation}")

    def _act_backward(self, dout: np.ndarray, x: np.ndarray) -> np.ndarray:
        cfg = self.config
        if cfg.activation == "gelu":
            return _gelu_backward(dout, x)
        elif cfg.activation == "silu":
            return _silu_backward(dout, x)
        elif cfg.activation == "geglu":
            return _geglu_backward(dout, x)
        else:
            raise ValueError(f"unknown activation: {cfg.activation}")

    # --------------------------------------------------
    def forward(self, ids: np.ndarray, kv_cache: Optional["KVCache"] = None, start_pos: int = 0) -> tuple:
        """Logits (B,T,V) + cache for backward. ids: int64 (B,T).
        
        If kv_cache is provided, uses cached K,V for positions < start_pos.
        Only computes attention for new tokens at positions >= start_pos.
        """
        cfg = self.config
        B, T = ids.shape
        dh = cfg.hidden_size // cfg.num_heads
        cache: dict = {"ids": ids}

        # Token embeddings
        x = self.params["tokE"][ids]

        # Positional embeddings
        if cfg.positional == "learned":
            if kv_cache is not None and start_pos > 0:
                # For KV cache continuation, use absolute positions
                x = x + self.params["posE"][start_pos:start_pos + T][None, :, :]
            else:
                x = x + self.params["posE"][:T][None, :, :]
        # RoPE and ALiBi are applied in attention

        for layer in range(cfg.num_layers):
            p = f"L{layer}."
            # Norm 1
            if cfg.normalization == "layernorm":
                h, ln_cache = self._norm_forward(x, self.params[p + "ln1W"], self.params[p + "ln1b"])
            else:
                h, ln_cache = self._norm_forward(x, self.params[p + "ln1W"])
            cache[p + "ln1"] = ln_cache
            cache[p + "xin"] = x

            # QKV projection
            qkv = h @ self.params[p + "qkvW"]
            if cfg.qkv_bias:
                qkv = qkv + self.params[p + "qkvb"]
            cache[p + "hq"] = h

            heads = qkv.reshape(B, T, cfg.num_heads, 3 * dh)
            q = heads[:, :, :, :dh].transpose(0, 2, 1, 3)
            k = heads[:, :, :, dh:2 * dh].transpose(0, 2, 1, 3)
            v = heads[:, :, :, 2 * dh:].transpose(0, 2, 1, 3)

            # Apply RoPE to NEW q,k with correct position offsets BEFORE KV cache handling
            if cfg.positional == "rope":
                q = _apply_rope_single(q, self._rope_cos, self._rope_sin, start_pos)
                k = _apply_rope_single(k, self._rope_cos, self._rope_sin, start_pos)

            # Handle KV cache
            if kv_cache is not None and start_pos > 0:
                # Get cached K,V up to start_pos (already have RoPE applied)
                cached_k, cached_v = kv_cache.get(layer, start_pos)
                # Concatenate cached with new (both have RoPE)
                k = np.concatenate([cached_k, k], axis=2)
                v = np.concatenate([cached_v, v], axis=2)
            
            # Update cache with NEW K,V only (they already have RoPE)
            if kv_cache is not None:
                # Write only the new K,V at position start_pos
                kv_cache.update(layer, k[:, :, -T:], v[:, :, -T:], start_pos)

            # Now k,v have shape (B, H, start_pos + T, dh)
            # q has shape (B, H, T, dh)
            # We need scores of shape (B, H, T, start_pos + T)
            scores = q @ k.transpose(0, 1, 3, 2) / float(np.sqrt(dh))

            if cfg.positional == "alibi":
                # ALiBi: linear bias per head
                full_T = start_pos + T
                slopes = self._alibi_slopes(cfg.num_heads)
                alibi_bias = slopes[None, :, None, None] * np.arange(full_T)[None, None, :, None]  # (1, H, full_T, 1)
                alibi_bias = alibi_bias - alibi_bias.transpose(0, 1, 3, 2)  # (1, H, full_T, full_T)
                # Slice to match scores shape (T, full_T)
                scores = scores + alibi_bias[:, :, :T, :].astype(scores.dtype)

            # Causal mask
            full_T = start_pos + T
            mask = np.triu(np.ones((T, full_T), dtype=bool), k=start_pos + 1)
            scores = np.where(mask[None, None, :, :], -1e9, scores)

            probs = _softmax(scores)
            cache[p + "att"] = (q, k, v, probs)
            ctx = (probs @ v).transpose(0, 2, 1, 3).reshape(B, T, cfg.hidden_size)

            # Attention output projection
            attn_out = ctx @ self.params[p + "oW"]
            if cfg.out_bias:
                attn_out = attn_out + self.params[p + "ob"]
            cache[p + "ctx"] = ctx

            # Residual 1
            x = x + attn_out

            # Norm 2
            if cfg.normalization == "layernorm":
                h2, ln_cache2 = self._norm_forward(x, self.params[p + "ln2W"], self.params[p + "ln2b"])
            else:
                h2, ln_cache2 = self._norm_forward(x, self.params[p + "ln2W"])
            cache[p + "ln2"] = ln_cache2
            cache[p + "xmid"] = x

            # FFN
            f1 = h2 @ self.params[p + "f1W"]
            if cfg.ffn_bias:
                f1 = f1 + self.params[p + "f1b"]
            cache[p + "h2"] = h2
            g = self._act_forward(f1)
            cache[p + "f1"] = f1
            f2 = g @ self.params[p + "f2W"]
            if cfg.ffn_bias:
                f2 = f2 + self.params[p + "f2b"]
            cache[p + "g"] = g

            # Residual 2
            x = x + f2

        # Final norm
        if cfg.normalization == "layernorm":
            hfin, ln_cache_f = self._norm_forward(x, self.params["lnfW"], self.params["lnfb"])
        else:
            hfin, ln_cache_f = self._norm_forward(x, self.params["lnfW"])
        cache["lnf"] = ln_cache_f
        cache["hfin_in"] = x

        # Output projection (tied or untied)
        if cfg.tied_embeddings:
            logits = hfin @ self.params["tokE"].T
        else:
            logits = hfin @ self.params["headW"]
            if cfg.out_bias:
                logits = logits + self.params["headb"]
        cache["hfin"] = hfin
        return logits, cache

    def _alibi_slopes(self, num_heads: int) -> np.ndarray:
        """ALiBi slopes: 2^(-8 * i / num_heads) for i=1..num_heads"""
        # From original ALiBi paper
        start = 2 ** (-(8 / num_heads))
        ratio = start
        slopes = np.array([start * (ratio ** i) for i in range(num_heads)], dtype=np.float32)
        return slopes

    # --------------------------------------------------
    def loss_and_backward(self, logits: np.ndarray, cache: dict,
                          targets: np.ndarray, ignore_id: int = -100) -> tuple:
        """Mean cross-entropy over non-ignored positions + full backward.

        Returns (loss, grads). Targets (B,T) with ignore_id skipped.
        """
        cfg = self.config
        B, T, V = logits.shape
        dh = cfg.hidden_size // cfg.num_heads
        flat_logits = logits.reshape(-1, V)
        flat_targets = targets.reshape(-1)
        keep = flat_targets != ignore_id
        if not bool(keep.any()):
            return 0.0, {k: np.zeros_like(v) for k, v in self.params.items()}
        kept_logits = flat_logits[keep]
        kept_targets = flat_targets[keep]
        probs = _softmax(kept_logits)
        n = kept_targets.shape[0]
        correct = probs[np.arange(n), kept_targets]
        loss = float(-np.log(np.maximum(correct, 1e-12)).mean())
        dlogits = probs
        dlogits[np.arange(n), kept_targets] -= 1.0
        dlogits /= n
        full = np.zeros_like(flat_logits)
        full[keep] = dlogits
        dlogits_bt = full.reshape(B, T, V)
        grads = {k: np.zeros_like(v) for k, v in self.params.items()}

        # Output projection grads
        dhfin = dlogits_bt @ (self.params["tokE"] if cfg.tied_embeddings else self.params["headW"]).T
        if cfg.tied_embeddings:
            grads["tokE"] += dlogits_bt.reshape(-1, V).T @ cache["hfin"].reshape(-1, cfg.hidden_size)
        else:
            grads["headW"] += cache["hfin"].reshape(-1, cfg.hidden_size).T @ dlogits_bt.reshape(-1, V)
            if cfg.out_bias:
                grads["headb"] += dlogits_bt.sum(axis=(0, 1))

        # Final norm backward
        dx, dlnfW, dlnfb = self._norm_backward(dhfin, cache["lnf"])
        grads["lnfW"] += dlnfW
        if cfg.normalization == "layernorm":
            grads["lnfb"] += dlnfb

        # Layer backward pass
        for layer in reversed(range(cfg.num_layers)):
            p = f"L{layer}."
            # FFN branch
            df2 = dx
            dg = df2 @ self.params[p + "f2W"].T
            if cfg.ffn_bias:
                grads[p + "f2b"] += df2.sum(axis=(0, 1))
            grads[p + "f2W"] += cache[p + "g"].reshape(-1, cfg.ffn_size).T @ df2.reshape(-1, cfg.hidden_size)

            df1 = self._act_backward(dg, cache[p + "f1"])
            if cfg.ffn_bias:
                grads[p + "f1b"] += df1.sum(axis=(0, 1))
            h2 = cache[p + "h2"]
            grads[p + "f1W"] += h2.reshape(-1, cfg.hidden_size).T @ df1.reshape(-1, df1.shape[-1])

            dh2 = df1 @ self.params[p + "f1W"].T
            dx_mid, dln2W, dln2b = self._norm_backward(dh2, cache[p + "ln2"])
            grads[p + "ln2W"] += dln2W
            if cfg.normalization == "layernorm":
                grads[p + "ln2b"] += dln2b

            dx = dx + dx_mid  # d(xmid): residual + FFN-norm paths

            # Attention branch
            d_attn = dx
            d_resid = dx
            ctx = cache[p + "ctx"]
            dctx = d_attn @ self.params[p + "oW"].T
            grads[p + "oW"] += ctx.reshape(-1, cfg.hidden_size).T @ d_attn.reshape(-1, cfg.hidden_size)
            if cfg.out_bias:
                grads[p + "ob"] += d_attn.sum(axis=(0, 1))

            B_, T_ = B, T
            dctx_h = dctx.reshape(B_, T_, cfg.num_heads, dh).transpose(0, 2, 1, 3)
            q, k, v, probs = cache[p + "att"]

            # Backward through attention
            dv_h = probs.transpose(0, 1, 3, 2) @ dctx_h
            dv = dv_h.transpose(0, 2, 1, 3).reshape(B_, T_, cfg.hidden_size)
            dprobs = dctx_h @ v.transpose(0, 1, 3, 2)

            # Softmax backward
            s = (dprobs * probs).sum(axis=-1, keepdims=True)
            dscores = probs * (dprobs - s)

            # Causal mask backward (zero out masked positions)
            mask = np.triu(np.ones((T_, T_), dtype=bool), k=1)
            dscores = np.where(mask[None, None, :, :], 0.0, dscores)

            # ALiBi backward (bias has no params, just passes through)
            # RoPE backward would need to be implemented if we train RoPE positions
            # For now, RoPE is fixed (non-learned), so no backward needed

            dq = (dscores @ k) / float(np.sqrt(dh))
            dk = (dscores.transpose(0, 1, 3, 2) @ q) / float(np.sqrt(dh))

            # QKV gradient
            dq_h = dq.transpose(0, 2, 1, 3)
            dk_h = dk.transpose(0, 2, 1, 3)
            dv_h2 = dv_h.transpose(0, 2, 1, 3)
            dqkv = np.concatenate([dq_h, dk_h, dv_h2], axis=-1).reshape(B_, T_, 3 * cfg.hidden_size)

            hq = cache[p + "hq"]
            grads[p + "qkvW"] += hq.reshape(-1, cfg.hidden_size).T @ dqkv.reshape(-1, 3 * cfg.hidden_size)
            if cfg.qkv_bias:
                grads[p + "qkvb"] += dqkv.sum(axis=(0, 1))

            dh_in = dqkv @ self.params[p + "qkvW"].T
            dx_ln, dln1W, dln1b = self._norm_backward(dh_in, cache[p + "ln1"])
            grads[p + "ln1W"] += dln1W
            if cfg.normalization == "layernorm":
                grads[p + "ln1b"] += dln1b

            dx = d_resid + dx_ln

        # Embedding grads
        ids = cache["ids"]
        demb = dx
        np.add.at(grads["tokE"], ids, demb)

        if cfg.positional == "learned":
            grads["posE"][:T] += demb.sum(axis=0)

        return loss, grads

    # --------------------------------------------------
    def clip_grads(self, grads: dict, max_norm: float) -> float:
        total = float(np.sqrt(sum(float((g ** 2).sum()) for g in grads.values())))
        if total > max_norm > 0:
            scale = max_norm / (total + 1e-12)
            for key in grads:
                grads[key] *= scale
        return total

    def adamw_step(self, grads: dict, lr: float, beta1: float = 0.9,
                   beta2: float = 0.999, eps: float = 1e-8,
                   weight_decay: float = 0.01) -> None:
        self._step_count += 1
        t = self._step_count
        for key, param in self.params.items():
            grad = grads[key]
            state = self.opt_state.setdefault(
                key, {"m": np.zeros_like(param), "v": np.zeros_like(param)})
            state["m"] = np.asarray(beta1 * state["m"] + (1.0 - beta1) * grad, dtype=np.float32)
            state["v"] = np.asarray(beta2 * state["v"] + (1.0 - beta2) * (grad * grad), dtype=np.float32)
            m_hat = state["m"] / (1.0 - beta1 ** t)
            v_hat = state["v"] / (1.0 - beta2 ** t)
            param *= (1.0 - lr * weight_decay)
            param -= lr * m_hat / (np.sqrt(v_hat) + eps)

    # --------------------------------------------------
    @np.errstate(all="ignore")
    def generate(self, start_ids: list, max_new_tokens: int = 32,
                 temperature: float = 1.0, seed: int = 0,
                 top_k: int = 0, top_p: float = 1.0,
                 use_kv_cache: bool = True) -> list:
        """Greedy (temperature<=0) or sampled continuation with optional KV cache."""
        rng = np.random.default_rng(seed)
        ids = list(int(i) for i in start_ids)
        ctx = int(self.config.context_length)
        
        # Initialize KV cache
        kv_cache = None
        if use_kv_cache:
            cfg = self.config
            kv_cache = KVCache(
                num_layers=cfg.num_layers,
                batch_size=1,
                max_seq_len=cfg.context_length,
                hidden_size=cfg.hidden_size,
                num_heads=cfg.num_heads,
                head_dim=cfg.hidden_size // cfg.num_heads,
            )
        
        # First forward pass with full prompt
        window = np.array(ids[-ctx:], dtype=np.int64)[None, :]
        logits, _ = self.forward(window, kv_cache=kv_cache, start_pos=0)
        
        for i in range(max_new_tokens):
            # Stop if context is full
            if len(ids) >= ctx:
                break
            
            next_logits = logits[0, -1].astype(np.float64)
            if temperature <= 0:
                nxt = int(np.argmax(next_logits))
            else:
                order = np.argsort(next_logits)[::-1]
                keep = np.ones(len(next_logits), dtype=bool)
                if top_k > 0:
                    keep[order[top_k:]] = False
                if top_p < 1.0:
                    scaled = next_logits / max(1e-6, temperature)
                    shifted = scaled - scaled.max()
                    exp = np.exp(shifted)
                    probs = exp / exp.sum()
                    ranked = probs[order]
                    cutoff = int(np.searchsorted(np.cumsum(ranked), top_p)) + 1
                    keep[order[cutoff:]] = False
                masked = np.where(keep, next_logits, -np.inf)
                scaled = masked / max(1e-6, temperature)
                shifted = scaled - np.nanmax(scaled)
                exp = np.exp(shifted)
                probs = exp / np.nansum(exp)
                nxt = int(rng.choice(len(probs), p=probs))
            
            ids.append(nxt)
            
            # Subsequent forward passes only process the new token with KV cache
            if kv_cache is not None:
                # Only feed the new token
                new_token = np.array([[nxt]], dtype=np.int64)
                logits, _ = self.forward(new_token, kv_cache=kv_cache, start_pos=len(ids) - 1)
            else:
                # Fallback to full window
                window = np.array(ids[-ctx:], dtype=np.int64)[None, :]
                logits, _ = self.forward(window)
            
            if nxt == 2:  # EOS
                break
        return ids

    def generate_batch(self, batch_ids: list, max_new_tokens: int = 32,
                       temperature: float = 0.0, seed: int = 0) -> list:
        return [self.generate(list(ids), max_new_tokens=max_new_tokens,
                              temperature=temperature, seed=seed + index)
                for index, ids in enumerate(batch_ids)]

    def score(self, start_ids: list, completion_ids: list) -> float:
        ids = np.array(list(int(i) for i in start_ids) +
                       list(int(i) for i in completion_ids), dtype=np.int64)[None, :]
        logits, _ = self.forward(ids)
        log_probs = logits[0] - logits[0].max(axis=-1, keepdims=True)
        log_probs = log_probs - np.log(np.exp(log_probs).sum(axis=-1, keepdims=True))
        start = len(start_ids)
        picks = [log_probs[start + i, completion_ids[i]]
                 for i in range(len(completion_ids))
                 if start + i < log_probs.shape[0]]
        if not picks:
            return float("-inf")
        return float(sum(picks) / len(picks))