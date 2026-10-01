from __future__ import annotations
"""FSDP / sharded-training scaffolding for HERCULE-LM (Phase 2I/3H).

Real ``torch.distributed.fsdp`` wrapping — no reimplementation of
sharding. Until DDP single-GPU correctness is green AND multi-GPU
hardware exists, this module reports NOT_IMPLEMENTED/NOT_RUN and its
wrapping entry point refuses to pretend.

 transformer auto-wrap policy targets the per-block modules
(``models.hercule_lm.torch_model._TorchBlock``) so each transformer
block becomes one sharded unit; embeddings/head stay replicated.
"""

from typing import Any, Dict


def fsdp_available() -> bool:
    try:
        import torch.distributed.fsdp  # noqa: F401

        return True
    except Exception:
        return False


def fsdp_status() -> Dict[str, Any]:
    """Honest FSDP capability report."""
    from .distributed import ddp_status

    dist = ddp_status()
    if dist["cuda_device_count"] >= 2 and fsdp_available():
        state = "READY (hardware present, no FSDP run yet)"
    elif not fsdp_available():
        state = "NOT_IMPLEMENTED (torch.distributed.fsdp unavailable)"
    else:
        state = "NOT_IMPLEMENTED (requires >= 2 CUDA devices + proven DDP)"
    return {"fsdp_available": fsdp_available(),
            "cuda_device_count": dist["cuda_device_count"],
            "distributed_status": dist["distributed_status"],
            "fsdp_status": state}


def block_wrap_policy():
    """Auto-wrap policy: one FSDP unit per transformer block."""
    try:
        from torch.distributed.fsdp.wrap import transformer_auto_wrap_policy

        from .torch_model import _TorchBlock

        return transformer_auto_wrap_policy(
            transformer_layer_cls={_TorchBlock})
    except Exception as exc:
        raise RuntimeError(f"FSDP_UNAVAILABLE: cannot build wrap policy ({exc})")


def wrap_fsdp(model, device=None, offload_cpu: bool = False):
    """Wrap a torch model with fully-sharded data parallel.

    Requires an initialized multi-rank process group; refuses
    single-process wrapping (that would be fake sharding).
    """
    from .distributed import get_world_size, is_dist_initialized

    if not fsdp_available():
        raise RuntimeError("FSDP_UNAVAILABLE: torch.distributed.fsdp not importable")
    if not is_dist_initialized() or get_world_size() < 2:
        raise RuntimeError("FSDP_UNAVAILABLE: FSDP requires an initialized process "
                           "group with world_size >= 2 (single-process wrapping "
                           "would be fake sharding)")
    from torch.distributed.fsdp import CPUOffload, FullyShardedDataParallel as FSDP
    from torch.distributed.fsdp import MixedPrecision

    return FSDP(
        model,
        auto_wrap_policy=block_wrap_policy(),
        cpu_offload=CPUOffload(offload_params=bool(offload_cpu)),
        mixed_precision=None,  # FP32 first; AMP only via explicit --amp runs
        device_id=device,
    )
