from __future__ import annotations
"""SFT + preference-learning infrastructure (Phase 6B/6G).

SFT reuses the proven torch trainer: conversation samples are rendered
as ``prompt + response`` token blocks with an SFT marker, and the
existing ``mask_before_marker`` + ``--sft-marker`` path trains on
responses only. Nothing in the optimizer, scheduler, checkpoint, or
resume path changes.

Preference learning (DPO-style) is provided as an explicit,
CPU-testable loss interface over paired samples — NOT a claim of RL
capability. Actual preference training + evaluation is required before
any improvement claim.
"""

from typing import Any, Dict, List, Sequence

SFT_MARKER = "<|response|>"


def render_sample(prompt: str, response: str,
                  marker: str = SFT_MARKER) -> str:
    """Single-turn conversation block: prompt + marker + response."""
    return f"{prompt.strip()}\n{marker}\n{response.strip()}\n"


def render_batch(samples: Sequence[Dict[str, Any]],
                 marker: str = SFT_MARKER) -> List[str]:
    return [render_sample(s["prompt"], s["response"], marker) for s in samples]


def sft_train_args(marker: str = SFT_MARKER) -> List[str]:
    """CLI fragment enabling response-only training in the torch trainer."""
    return ["--sft-marker", marker]


def run_sft(args, samples: Sequence[Dict[str, Any]],
            tokenizer, seq_len: int, seed: int = 0):
    """Encode rendered samples into (xs, ys) pairs with marker masking.

    Pure data preparation (no training): proves the SFT masking path on
    CPU without a GPU run. Returns (num_pairs, masked_fraction).
    """
    from .data import mask_before_marker

    marker_ids = tokenizer.encode(SFT_MARKER)
    pairs = masked = total = 0
    for text in render_batch(samples):
        ids = tokenizer.encode(text, add_eos=True)
        if len(ids) < seq_len + 1:
            continue
        import numpy as np

        arr = np.asarray(ids[:seq_len + 1], dtype=np.int64)
        xs, ys = arr[:-1].reshape(1, -1), arr[1:].reshape(1, -1)
        masked_labels = mask_before_marker(ys, marker_ids)
        total += int(masked_labels.size)
        masked += int((masked_labels == -100).sum())
        pairs += 1
    return {"pairs": pairs,
            "masked_fraction": round(masked / max(1, total), 3),
            "marker_ids": marker_ids}


# -------------------------------------------------- preference interfaces

def dpo_loss(chosen_logp: float, rejected_logp: float,
             ref_chosen_logp: float = 0.0, ref_rejected_logp: float = 0.0,
             beta: float = 0.1) -> Dict[str, Any]:
    """DPO-style pairwise loss on log-probs (pure math, backend-agnostic).

    loss = -log sigmoid(beta * ((chosen - rejected) - (ref_c - ref_r))).
    No training loop attached: callers must run + evaluate real
    optimization before claiming preference learning works.
    """
    import math

    margin = (chosen_logp - rejected_logp) - (ref_chosen_logp - ref_rejected_logp)
    loss = -math.log(1e-12 + 1.0 / (1.0 + math.exp(-beta * margin)))
    return {"loss": loss, "margin": margin, "beta": beta}


def preference_record(prompt: str, chosen: str, rejected: str,
                      annotator: str = "hercule-synthetic-v1") -> Dict[str, Any]:
    import hashlib

    rid = hashlib.sha256(f"{prompt}\x00{chosen}\x00{rejected}".encode()).hexdigest()[:16]
    return {"id": rid, "prompt": prompt, "chosen": chosen,
            "rejected": rejected, "annotator": annotator,
            "license": "HERCULE-authored (MIT, repo)"}


class RewardModelInterface:
    """Outcome-based reward interface: score(prompt, completion) -> float.

    The reference implementation scores via verifiers (verifiable
    outcomes only). Learned reward models plug in by subclassing.
    """

    def score(self, prompt: str, completion: str,
              context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        from . import verifiers as _v

        ctx = dict(context or {})
        kind = ctx.get("verifier", "none")
        if kind == "math":
            return _v.verify_math(completion, ctx.get("reference", ""))
        if kind == "json":
            return _v.verify_json(completion, ctx.get("schema"))
        if kind == "tool":
            return _v.verify_tool_call(completion, ctx.get("allowed"))
        if kind == "tests":
            return _v.verify_python_tests(ctx.get("code", completion),
                                          ctx.get("tests", []))
        if kind == "refusal":
            return _v.verify_refusal(completion)
        if kind == "citation":
            return _v.verify_citation(completion, ctx.get("reference", ""))
        return {"pass": None, "score": 0.0,
                "detail": "no verifier bound (not a reward claim)"}
