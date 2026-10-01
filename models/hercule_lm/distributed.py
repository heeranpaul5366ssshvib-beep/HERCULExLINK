from __future__ import annotations
"""Distributed training foundation for HERCULE-LM (Phase 2H/3G).

Genuine PyTorch DistributedDataParallel scaffolding:

- process-group init from env (torchrun or explicit RANK/WORLD_SIZE)
- rank / local-rank / world-size handling
- per-rank device assignment (cuda:N by local rank)
- gradient synchronization via DDP (all-reduce, proven by torch)
- rank-sharded batch iteration (each rank consumes its own slice)
- rank-safe logging (rank 0 only) and checkpointing
- barrier + clean shutdown + failure surfacing

Honesty rules enforced here:
- single-process runs report world_size=1, rank=0, distributed=OFF
- CPU/gloo multi-process runs are HARNESS validation only — they prove
  the launch/sync/checkpoint plumbing, never "multi-GPU training"
- multi-GPU is claimed only after a real run on >= 2 CUDA devices;
  until then ``ddp_status()`` reports NOT_IMPLEMENTED/NOT_RUN
"""

import os
from typing import Any, Dict, List, Optional, Tuple


def dist_available() -> bool:
    try:
        import torch.distributed as dist

        return bool(dist.is_available())
    except Exception:
        return False


def env_world_size() -> int:
    try:
        return max(1, int(os.environ.get("WORLD_SIZE", "1")))
    except (TypeError, ValueError):
        return 1


def wants_distributed() -> bool:
    """True when launched under torchrun/torch.distributed (WORLD_SIZE>1)."""
    return env_world_size() > 1


def get_rank() -> int:
    try:
        return max(0, int(os.environ.get("RANK", "0")))
    except (TypeError, ValueError):
        return 0


def get_local_rank() -> int:
    try:
        return max(0, int(os.environ.get("LOCAL_RANK", "0")))
    except (TypeError, ValueError):
        return 0


def get_world_size() -> int:
    if dist_available():
        try:
            import torch.distributed as dist

            if dist.is_initialized():
                return int(dist.get_world_size())
        except Exception:
            pass
    return env_world_size()


def is_main() -> bool:
    return get_rank() == 0


def is_dist_initialized() -> bool:
    try:
        import torch.distributed as dist

        return bool(dist.is_initialized())
    except Exception:
        return False


def backend_for(device: str) -> str:
    """nccl for CUDA, gloo for CPU. gloo is harness-only (never GPU proof)."""
    return "nccl" if str(device).startswith("cuda") else "gloo"


def init_process_group(device: str = "cpu",
                       timeout_s: float = 1800.0) -> Dict[str, Any]:
    """Init the default process group from env. Fails clearly on misuse.

    Requires WORLD_SIZE>1 (else returns a single-process record without
    initializing anything). CUDA ranks require CUDA; a local rank beyond
    the visible GPU count fails instead of silently remapping.
    """
    import datetime

    import torch

    info: Dict[str, Any] = {
        "world_size": 1, "rank": 0, "local_rank": 0,
        "backend": "none", "device": str(device),
        "distributed": "OFF (single process)",
    }
    if not wants_distributed():
        return info
    if not dist_available():
        raise RuntimeError("DISTRIBUTED_UNAVAILABLE: torch.distributed not available")
    rank, local_rank = get_rank(), get_local_rank()
    world = env_world_size()
    backend = backend_for(device)
    if backend == "nccl":
        if not torch.cuda.is_available():
            raise RuntimeError("DISTRIBUTED_UNAVAILABLE: nccl rank requested but "
                               "torch.cuda.is_available() is false")
        if local_rank >= torch.cuda.device_count():
            raise RuntimeError(
                f"DISTRIBUTED_UNAVAILABLE: local_rank {local_rank} out of range "
                f"(cuda device_count={torch.cuda.device_count()})")
        torch.cuda.set_device(local_rank)
    import torch.distributed as dist

    dist.init_process_group(
        backend=backend,
        init_method="env://",
        world_size=world,
        rank=rank,
        timeout=datetime.timedelta(seconds=float(timeout_s)),
    )
    info.update({
        "world_size": world, "rank": rank, "local_rank": local_rank,
        "backend": backend,
        "device": f"cuda:{local_rank}" if backend == "nccl" else "cpu",
        "distributed": f"ON ({backend}, world_size={world})",
    })
    return info


def barrier() -> None:
    try:
        import torch.distributed as dist

        if dist.is_initialized():
            dist.barrier()
    except Exception:
        pass


def cleanup() -> None:
    try:
        import torch.distributed as dist

        if dist.is_initialized():
            dist.destroy_process_group()
    except Exception:
        pass


def log_main(*parts) -> None:
    if is_main():
        print(*parts, flush=True)


def shard_batches(batches: list, rank: Optional[int] = None,
                  world: Optional[int] = None) -> list:
    """Rank-sharded view of the micro-batch list (round-robin).

    Deterministic per (rank, world); rank 0 with world 1 keeps all.
    """
    rank = get_rank() if rank is None else int(rank)
    world = get_world_size() if world is None else int(world)
    if world <= 1:
        return list(batches)
    return [batches[i] for i in range(len(batches)) if i % world == rank]


def wrap_ddp(model, device_ids=None, output_device=None):
    """Wrap a torch model in DistributedDataParallel (real gradient sync)."""
    from torch.nn.parallel import DistributedDataParallel as DDP

    if not is_dist_initialized():
        raise RuntimeError("DISTRIBUTED_UNAVAILABLE: process group not initialized "
                           "(launch with torchrun / WORLD_SIZE>1)")
    return DDP(model, device_ids=device_ids, output_device=output_device)


def average_object(value: Any) -> Any:
    """All-reduce a scalar tensor across ranks (mean); passthrough if solo."""
    try:
        import torch
        import torch.distributed as dist

        if dist.is_initialized():
            tensor = torch.tensor([float(value)], dtype=torch.float64)
            if torch.cuda.is_available():
                tensor = tensor.cuda()
            dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
            return float(tensor.item()) / dist.get_world_size()
    except Exception:
        pass
    return value


def ddp_status() -> Dict[str, Any]:
    """Honest distributed capability report (never claims GPUs)."""
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        count = int(torch.cuda.device_count()) if cuda else 0
    except Exception:
        cuda, count = False, 0
    initialized = is_dist_initialized()
    world = get_world_size() if initialized else env_world_size()
    if count >= 2 and initialized:
        state = "IMPLEMENTED (multi-GPU run active)"
    elif count >= 2:
        state = "READY (hardware present, no multi-GPU run yet)"
    elif initialized and world > 1:
        state = "HARNESS (multi-process CPU/gloo plumbing only, NOT multi-GPU proof)"
    else:
        state = "NOT_IMPLEMENTED (single-device only)"
    return {"world_size": world if initialized else 1,
            "rank": get_rank() if initialized else 0,
            "local_rank": get_local_rank() if initialized else 0,
            "cuda_available": cuda,
            "cuda_device_count": count,
            "process_group": "initialized" if initialized else "none",
            "distributed_status": state}


def broadcast_object(value: Any, src: int = 0) -> Any:
    """Broadcast a picklable object from src rank (passthrough if solo)."""
    try:
        import torch.distributed as dist

        if dist.is_initialized():
            container: List[Any] = [value]
            dist.broadcast_object_list(container, src=src)
            return container[0]
    except Exception:
        pass
    return value


def all_gather_object(value: Any) -> List[Any]:
    """Gather picklable objects from all ranks (solo -> [value])."""
    try:
        import torch.distributed as dist

        if dist.is_initialized():
            out: List[Any] = [None] * dist.get_world_size()
            dist.all_gather_object(out, value)
            return out
    except Exception:
        pass
    return [value]


def seed_for_rank(base_seed: int) -> int:
    """Rank-offset seed so ranks differ where they must (data order stays shared)."""
    return int(base_seed) + 1000 * get_rank()


def device_for_rank(requested: str) -> Tuple[str, bool]:
    """Resolve the torch device string for this rank.

    Returns (device_string, is_distributed). cuda:N requests map N ->
    this rank's local GPU; a bare "cuda" maps to cuda:<local_rank>.
    """
    want = str(requested or "auto").strip().lower()
    if wants_distributed() and (want == "cuda" or want.startswith("cuda:")):
        return f"cuda:{get_local_rank()}", True
    return want, wants_distributed()
