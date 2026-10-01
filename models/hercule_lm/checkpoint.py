from __future__ import annotations
"""HERCULE-LM checkpoint format (N3 §13, N9-CAP §8): atomic, self-describing, with lineage.

Each checkpoint directory holds ``weights.npz`` + ``manifest.json``;
``latest.json`` points at the newest VALIDATED checkpoint but is
never the only copy. Writes are atomic (tmp + replace); resume
validates architecture/dataset identity before accepting state.

Lineage: each checkpoint records its parent checkpoint, enabling
full experiment genealogy tracking.
"""

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_checkpoint(directory: str, model, tokenizer_manifest: dict,
                    dataset: dict, train_state: dict,
                    run_manifest: dict) -> str:
    """Persist model + optimizer + manifests atomically. Returns dir."""
    import numpy as np

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    weights = {k: np.asarray(v, dtype=np.float32) for k, v in model.params.items()}
    opt: Dict[str, Any] = {}
    for key, state in model.opt_state.items():
        opt[f"opt_{key}_m"] = np.asarray(state["m"], dtype=np.float32)
        opt[f"opt_{key}_v"] = np.asarray(state["v"], dtype=np.float32)
    manifest = {
        "model_id": model.config.model_id,
        "architecture": model.config.as_dict(),
        "architecture_hash": model.config.architecture_hash(),
        "parameter_count": model.parameter_count(),
        "seed": model.seed,
        "tokenizer": dict(tokenizer_manifest or {}),
        "dataset": dict(dataset or {}),
        "train_state": dict(train_state or {}),
        "run": dict(run_manifest or {}),
        "created_at": _utcnow(),
        "origin": "hercule-lm random initialization (no pretrained weights)",
        "checkpoint_format": "hercule-npz-v1",
        "scaler": None,  # AMP scaler state would live here on torch paths
        "rng": {"python": "see run record", "numpy": "see run record",
                "note": "CPU streams reproducible under fixed seed+order; "
                        "CUDA trajectories are NOT claimed bit-identical"},
        "origin_device": str((dict(run_manifest or {}).get("device") or "cpu")),
    }
    tmp_weights = target / "weights.inprogress.npz"
    np.savez_compressed(tmp_weights, **weights, **opt)
    tmp_weights.replace(target / "weights.npz")
    (target / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    manifest["weights_sha256"] = _sha256_file(target / "weights.npz")
    (target / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return str(target)


TORCH_FORMAT = "hercule-torch-v1"
NPZ_FORMAT = "hercule-npz-v1"
LINEAGE_VERSION = "hercule-lineage-v1"


@dataclass
class CheckpointLineage:
    """Lineage information for a checkpoint."""
    checkpoint_id: str              # Unique ID for this checkpoint (e.g., step_00000200)
    parent_checkpoint_id: Optional[str] = None  # Parent checkpoint ID
    parent_step: Optional[int] = None  # Parent step number
    lineage_root: Optional[str] = None  # Root checkpoint of this lineage
    lineage_depth: int = 0          # Distance from root
    branch_name: str = "main"       # Branch identifier
    tags: List[str] = field(default_factory=list)  # User tags
    created_at: str = ""            # ISO timestamp
    experiment_id: str = ""         # Experiment identifier
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointLineage":
        return cls(**data)


@dataclass
class ExperimentManifest:
    """Complete experiment metadata for reproducibility."""
    experiment_id: str
    name: str
    description: str
    created_at: str
    config: Dict[str, Any]          # Full model config
    dataset_hash: str               # Dataset hash
    tokenizer_checksum: str         # Tokenizer checksum
    seed: int
    git_commit: str = ""            # Git commit if available
    tags: List[str] = field(default_factory=list)
    checkpoints: List[str] = field(default_factory=list)  # Checkpoint IDs in this experiment
    lineage_root: str = ""          # Root checkpoint
    metrics: Dict[str, Any] = field(default_factory=dict)  # Final metrics
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentManifest":
        return cls(**data)

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_cuda_map_target(map_to: str) -> str:
    """Validate an explicit CUDA map target; fail clearly, never remap silently."""
    wanted = str(map_to or "cpu").strip().lower()
    if wanted == "cpu":
        return "cpu"
    try:
        import torch

        if not torch.cuda.is_available():
            raise ValueError(
                f"CHECKPOINT_MAP_FAILED: target device '{map_to}' "
                f"unavailable (torch.cuda.is_available() is false)")
        if wanted.startswith("cuda:"):
            try:
                index = int(wanted.split(":", 1)[1])
            except ValueError:
                raise ValueError(
                    f"CHECKPOINT_MAP_FAILED: invalid target device '{map_to}'")
            if index >= torch.cuda.device_count():
                raise ValueError(
                    f"CHECKPOINT_MAP_FAILED: cuda:{index} out of range "
                    f"(count={torch.cuda.device_count()})")
        elif wanted != "cuda":
            raise ValueError(
                f"CHECKPOINT_MAP_FAILED: invalid target device '{map_to}' "
                f"(expected cpu|cuda|cuda:N)")
        return wanted
    except ValueError:
        raise
    except Exception:
        raise ValueError(
            f"CHECKPOINT_MAP_FAILED: target device '{map_to}' "
            f"unavailable (no torch/CUDA here)")


def _check_manifest_identity(manifest: Dict[str, Any], model, strict: bool,
                             expected_tokenizer_checksum: str,
                             expected_dataset_hash: str) -> None:
    if strict:
        if manifest.get("architecture_hash") != model.config.architecture_hash():
            raise ValueError("CHECKPOINT_MISMATCH: architecture hash differs "
                             f"({manifest.get('architecture_hash')} vs "
                             f"{model.config.architecture_hash()})")
        if "random initialization" not in manifest.get("origin", ""):
            raise ValueError("CHECKPOINT_MISMATCH: not a HERCULE-LM checkpoint")
    if expected_tokenizer_checksum:
        got = str((manifest.get("tokenizer") or {}).get("checksum", ""))
        if got != expected_tokenizer_checksum:
            raise ValueError("TOKENIZER_MISMATCH: checkpoint tokenizer "
                             f"{got!r} != expected {expected_tokenizer_checksum!r}")
    if expected_dataset_hash:
        got = str((manifest.get("dataset") or {}).get("dataset_hash",
                                                      (manifest.get("dataset") or {}).get("hash", "")))
        if got and got != expected_dataset_hash:
            raise ValueError("DATASET_HASH_MISMATCH: checkpoint dataset "
                             f"{got!r} != expected {expected_dataset_hash!r}")


def save_torch_checkpoint(directory: str, model, tokenizer_manifest: dict,
                          dataset: dict, train_state: dict,
                          run_manifest: dict, optimizer=None, scaler=None,
                          rng_state: Optional[dict] = None) -> str:
    """Persist a torch-backend checkpoint atomically. Returns dir.

    Layout: ``weights.pt`` (native: model + optimizer + RNG state) plus
    ``weights.npz`` (params-only export so the NumPy reference backend
    can load the same point explicitly) plus ``manifest.json`` with
    ``checkpoint_format="hercule-torch-v1"``. Existing
    ``hercule-npz-v1`` checkpoints are untouched and remain loadable.
    """
    import numpy as np
    import torch

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    run = dict(run_manifest or {})
    try:
        device_str = str(next(model.parameters()).device)
    except StopIteration:
        device_str = "cpu"
    # The manifest must stay JSON: describe RNG state by shape/seed here;
    # the live tensors travel inside weights.pt only.
    rng_state = dict(rng_state or {})

    def _rng_summary(value):
        try:
            import torch as _torch

            if isinstance(value, _torch.Tensor):
                return {"kind": "torch-rng-state", "shape": list(value.shape),
                        "dtype": str(value.dtype)}
        except Exception:
            pass
        if isinstance(value, (list, tuple)):
            return {"kind": "rng-list", "length": len(value)}
        return value if isinstance(value, (int, float, str, bool, type(None))) else str(value)

    rng_summary = {k: _rng_summary(v) for k, v in rng_state.items()}
    manifest = {
        "model_id": model.config.model_id,
        "architecture": model.config.as_dict(),
        "architecture_hash": model.config.architecture_hash(),
        "parameter_count": model.parameter_count(),
        "seed": model.seed,
        "tokenizer": dict(tokenizer_manifest or {}),
        "dataset": dict(dataset or {}),
        "train_state": dict(train_state or {}),
        "run": run,
        "created_at": _utcnow(),
        "origin": "hercule-lm random initialization (no pretrained weights)",
        "checkpoint_format": TORCH_FORMAT,
        "backend": "torch",
        "device": run.get("device", device_str),
        "dtype": run.get("dtype", "float32"),
        "amp": run.get("amp", "off"),
        "scaler": None,
        "rng": rng_summary,
        "origin_device": str(run.get("device") or device_str),
        "npz_compat": "weights.npz holds params only (optimizer state is "
                      "torch-native in weights.pt); NumPy loads resume with "
                      "a fresh optimizer unless converted explicitly",
    }
    try:
        cpu_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
    except Exception:
        cpu_state = {k: v.cpu() for k, v in model.state_dict().items()}
    payload = {"state_dict": cpu_state,
               "step": int((dict(train_state or {})).get("step", 0)),
               "rng_state": dict(rng_state or {})}
    if optimizer is not None:
        try:
            payload["optimizer"] = optimizer.state_dict()
        except Exception:
            payload["optimizer"] = None
    if scaler is not None:
        try:
            payload["scaler"] = scaler.state_dict()
            manifest["scaler"] = "torch.cuda.amp.GradScaler state in weights.pt"
        except Exception:
            payload["scaler"] = None
    tmp_pt = target / "weights.inprogress.pt"
    torch.save(payload, tmp_pt)
    tmp_pt.replace(target / "weights.pt")
    # Params-only .npz export for explicit NumPy-side loading.
    weights = {k: np.asarray(v, dtype=np.float32)
               for k, v in model.numpy_param_dict().items()}
    tmp_npz = target / "weights.inprogress.npz"
    np.savez_compressed(tmp_npz, **weights)
    tmp_npz.replace(target / "weights.npz")
    (target / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    manifest["weights_sha256"] = _sha256_file(target / "weights.pt")
    manifest["weights_npz_sha256"] = _sha256_file(target / "weights.npz")
    (target / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return str(target)


def load_torch_checkpoint(directory: str, model, optimizer=None,
                          strict: bool = True, map_to: str = "cpu",
                          expected_tokenizer_checksum: str = "",
                          expected_dataset_hash: str = "",
                          load_optimizer: bool = True,
                          load_rng: bool = True) -> Dict[str, Any]:
    """Load a torch checkpoint into an initialized torch model.

    Prefers native ``weights.pt``; falls back to an explicit
    ``weights.npz`` conversion (params only, fresh optimizer) when no
    ``.pt`` is present — e.g. resuming a NumPy run on the torch
    backend. ``map_to`` (cpu|cuda|cuda:N) is explicit and safe; CUDA
    targets fail clearly without CUDA. Returns the manifest with a
    ``_load`` record describing the source and mapping used.
    """
    import numpy as np
    import torch

    wanted = _check_cuda_map_target(map_to)
    target = Path(directory)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    _check_manifest_identity(manifest, model, strict,
                             expected_tokenizer_checksum,
                             expected_dataset_hash)
    fmt = manifest.get("checkpoint_format", NPZ_FORMAT)
    pt_path = target / "weights.pt"
    used_source = ""
    if pt_path.exists():
        payload = torch.load(str(pt_path), map_location=wanted, weights_only=False)
        model.load_state_dict(payload["state_dict"], strict=True)
        used_source = TORCH_FORMAT
        if optimizer is not None and load_optimizer and payload.get("optimizer"):
            try:
                optimizer.load_state_dict(payload["optimizer"])
            except Exception as exc:
                raise ValueError(f"CHECKPOINT_CORRUPTED: optimizer state mismatch ({exc})")
        if load_rng and isinstance(payload.get("rng_state"), dict):
            _restore_torch_rng(payload["rng_state"])
    elif (target / "weights.npz").exists():
        # Explicit cross-backend conversion: NumPy weights -> torch params.
        blob = np.load(target / "weights.npz")
        model.load_numpy_param_dict({k: np.asarray(blob[k], dtype=np.float32)
                                     for k in blob.files}, strict=True)
        used_source = NPZ_FORMAT + "+explicit-npz-to-torch"
    else:
        raise ValueError("CHECKPOINT_CORRUPTED: no weights.pt or weights.npz found")
    if wanted != "cpu":
        model.to(wanted)
    try:
        model._step_count = int(manifest.get("train_state", {}).get("step", 0))
    except (TypeError, ValueError):
        model._step_count = 0
    manifest["_load"] = {"source_format": used_source,
                         "manifest_format": fmt,
                         "map_to": wanted,
                         "origin_device": manifest.get("origin_device", "?")}
    return manifest


def _restore_torch_rng(rng_state: dict) -> None:
    """Best-effort torch RNG restore (never crashes a resume)."""
    try:
        import torch

        if rng_state.get("torch_cpu") is not None:
            torch.set_rng_state(rng_state["torch_cpu"])
        if rng_state.get("torch_cuda") is not None and torch.cuda.is_available():
            try:
                torch.cuda.set_rng_state_all(rng_state["torch_cuda"])
            except Exception:
                pass
    except Exception:
        pass


def capture_torch_rng() -> dict:
    """Snapshot torch-side RNG state (JSON-hostile tensors kept as tensors)."""
    try:
        import torch

        state: Dict[str, Any] = {"torch_cpu": torch.get_rng_state()}
        if torch.cuda.is_available():
            try:
                state["torch_cuda"] = torch.cuda.get_rng_state_all()
            except Exception:
                pass
        return state
    except Exception:
        return {}


def load_checkpoint(directory: str, model, strict: bool = True,
                    map_to: str = "cpu",
                    expected_tokenizer_checksum: str = "",
                    expected_dataset_hash: str = "") -> Dict[str, Any]:
    """Load weights (+optimizer when present) into an initialized model.

    ``map_to`` selects the target device explicitly ("cpu" always
    works; "cuda*" requires torch+CUDA and fails clearly otherwise —
    never silent remapping). Numpy weights carry no device tags, so
    CPU↔CUDA migration is a load-time placement decision, which this
    parameter records. Tokenizer/dataset identity mismatches fail
    clearly instead of silently mixing artifacts.

    Torch models (``TorchHerculeLM``) accept ``map_to="cuda*"`` on
    CUDA builds; the NumPy reference model is CPU-only, so a CUDA
    target for it fails with CHECKPOINT_MAP_FAILED.
    """
    import numpy as np

    wanted = str(map_to or "cpu").strip().lower()
    try:
        from .torch_model import TorchHerculeLM  # local import: torch optional
    except Exception:
        TorchHerculeLM = None  # type: ignore
    if TorchHerculeLM is not None and isinstance(model, TorchHerculeLM):
        # Torch models use the native loader (weights.pt preferred, explicit
        # .npz conversion otherwise); optimizer/RNG restore needs the live
        # optimizer, so this path loads params (+RNG) only.
        return load_torch_checkpoint(directory, model, optimizer=None,
                                     strict=strict, map_to=map_to,
                                     expected_tokenizer_checksum=expected_tokenizer_checksum,
                                     expected_dataset_hash=expected_dataset_hash,
                                     load_optimizer=False, load_rng=True)
    if wanted != "cpu":
        _check_cuda_map_target(map_to)  # fails clearly without CUDA
        raise ValueError(
            f"CHECKPOINT_MAP_FAILED: target device '{map_to}' "
            f"requires a torch-backend model (NumPy reference is CPU-only)")
    target = Path(directory)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    if strict:
        if manifest.get("architecture_hash") != model.config.architecture_hash():
            raise ValueError("CHECKPOINT_MISMATCH: architecture hash differs "
                             f"({manifest.get('architecture_hash')} vs "
                             f"{model.config.architecture_hash()})")
        if "random initialization" not in manifest.get("origin", ""):
            raise ValueError("CHECKPOINT_MISMATCH: not a HERCULE-LM checkpoint")
    if expected_tokenizer_checksum:
        got = str((manifest.get("tokenizer") or {}).get("checksum", ""))
        if got != expected_tokenizer_checksum:
            raise ValueError("TOKENIZER_MISMATCH: checkpoint tokenizer "
                             f"{got!r} != expected {expected_tokenizer_checksum!r}")
    if expected_dataset_hash:
        got = str((manifest.get("dataset") or {}).get("dataset_hash",
                                                      (manifest.get("dataset") or {}).get("hash", "")))
        if got and got != expected_dataset_hash:
            raise ValueError("DATASET_HASH_MISMATCH: checkpoint dataset "
                             f"{got!r} != expected {expected_dataset_hash!r}")
    blob = np.load(target / "weights.npz")
    for key in list(model.params.keys()):
        if key not in blob:
            raise ValueError(f"CHECKPOINT_CORRUPTED: missing param {key}")
        model.params[key] = np.asarray(blob[key], dtype=np.float32)
    # Optimizer state keys are stored flat as opt_<param>_{m,v}; restore best-effort.
    for key in list(model.params.keys()):
        entry = model.opt_state.setdefault(
            key, {"m": np.zeros_like(model.params[key]),
                  "v": np.zeros_like(model.params[key])})
        if f"opt_{key}_m" in blob:
            entry["m"] = np.asarray(blob[f"opt_{key}_m"], dtype=np.float32)
        if f"opt_{key}_v" in blob:
            entry["v"] = np.asarray(blob[f"opt_{key}_v"], dtype=np.float32)
    try:
        model._step_count = int(manifest.get("train_state", {}).get("step", 0))
    except (TypeError, ValueError):
        model._step_count = 0
    return manifest


def write_latest(root: str, checkpoint_dir: str) -> str:
    root_path = Path(root)
    latest = {"latest": str(checkpoint_dir), "updated_at": _utcnow()}
    (root_path / "latest.json").write_text(json.dumps(latest, indent=1), encoding="utf-8")
    return str(root_path / "latest.json")


def read_latest(root: str) -> Optional[str]:
    try:
        data = json.loads((Path(root) / "latest.json").read_text(encoding="utf-8"))
        return str(data.get("latest", "") or "") or None
    except (OSError, ValueError):
        return None


# --------------------------------------------------
# Lineage Functions

def get_checkpoint_id(directory: str) -> str:
    """Extract checkpoint ID from directory path."""
    return Path(directory).name


def save_lineage(directory: str, lineage: CheckpointLineage) -> str:
    """Save lineage info to checkpoint directory."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    lineage_path = target / "lineage.json"
    lineage.created_at = _utcnow()
    lineage.checkpoint_id = get_checkpoint_id(directory)
    lineage_path.write_text(json.dumps(lineage.to_dict(), indent=1), encoding="utf-8")
    return str(lineage_path)


def load_lineage(directory: str) -> Optional[CheckpointLineage]:
    """Load lineage info from checkpoint directory."""
    lineage_path = Path(directory) / "lineage.json"
    if not lineage_path.exists():
        return None
    try:
        data = json.loads(lineage_path.read_text(encoding="utf-8"))
        return CheckpointLineage.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


def create_lineage(
    checkpoint_dir: str,
    parent_checkpoint_dir: Optional[str] = None,
    experiment_id: str = "",
    branch_name: str = "main",
    tags: Optional[List[str]] = None
) -> CheckpointLineage:
    """Create lineage info for a new checkpoint."""
    checkpoint_id = get_checkpoint_id(checkpoint_dir)
    
    lineage = CheckpointLineage(
        checkpoint_id=checkpoint_id,
        parent_checkpoint_id=get_checkpoint_id(parent_checkpoint_dir) if parent_checkpoint_dir else None,
        branch_name=branch_name,
        tags=tags or [],
        experiment_id=experiment_id,
        created_at=_utcnow()
    )
    
    if parent_checkpoint_dir:
        parent_lineage = load_lineage(parent_checkpoint_dir)
        if parent_lineage:
            lineage.parent_step = parent_lineage.checkpoint_id
            lineage.lineage_root = parent_lineage.lineage_root or parent_lineage.checkpoint_id
            lineage.lineage_depth = parent_lineage.lineage_depth + 1
        else:
            lineage.lineage_root = checkpoint_id
            lineage.lineage_depth = 0
    else:
        lineage.lineage_root = checkpoint_id
        lineage.lineage_depth = 0
    
    save_lineage(checkpoint_dir, lineage)
    return lineage


def trace_lineage(directory: str, max_depth: int = 100) -> List[CheckpointLineage]:
    """Trace lineage from a checkpoint back to root."""
    lineage_chain = []
    current_dir = directory
    depth = 0
    
    while current_dir and depth < max_depth:
        lineage = load_lineage(current_dir)
        if not lineage:
            break
        lineage_chain.append(lineage)
        
        if lineage.parent_checkpoint_id:
            # Find parent directory
            parent_path = Path(current_dir).parent / lineage.parent_checkpoint_id
            if parent_path.exists():
                current_dir = str(parent_path)
            else:
                # Try to find in checkpoints root
                checkpoints_root = Path(current_dir).parent.parent
                parent_path = checkpoints_root / lineage.parent_checkpoint_id
                if parent_path.exists():
                    current_dir = str(parent_path)
                else:
                    break
        else:
            break
        depth += 1
    
    return lineage_chain


def save_experiment_manifest(root: str, manifest: ExperimentManifest) -> str:
    """Save experiment manifest to checkpoints root."""
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    manifest_path = root_path / "experiments" / f"{manifest.experiment_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=1), encoding="utf-8")
    return str(manifest_path)


def load_experiment_manifest(root: str, experiment_id: str) -> Optional[ExperimentManifest]:
    """Load experiment manifest."""
    manifest_path = Path(root) / "experiments" / f"{experiment_id}.json"
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ExperimentManifest.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


def list_experiment_manifests(root: str) -> List[ExperimentManifest]:
    """List all experiment manifests."""
    experiments_dir = Path(root) / "experiments"
    if not experiments_dir.exists():
        return []
    manifests = []
    for path in experiments_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            manifests.append(ExperimentManifest.from_dict(data))
        except (json.JSONDecodeError, OSError):
            continue
    return manifests


def register_checkpoint_to_experiment(root: str, experiment_id: str, checkpoint_dir: str) -> None:
    """Register a checkpoint to an experiment manifest."""
    manifest = load_experiment_manifest(root, experiment_id)
    if not manifest:
        # Create new manifest
        manifest = ExperimentManifest(
            experiment_id=experiment_id,
            name=f"Experiment {experiment_id}",
            description="",
            created_at=_utcnow(),
            config={},
            dataset_hash="",
            tokenizer_checksum="",
            seed=0
        )
    checkpoint_id = get_checkpoint_id(checkpoint_dir)
    if checkpoint_id not in manifest.checkpoints:
        manifest.checkpoints.append(checkpoint_id)
    if not manifest.lineage_root:
        lineage = load_lineage(checkpoint_dir)
        if lineage:
            manifest.lineage_root = lineage.lineage_root or checkpoint_id
    save_experiment_manifest(root, manifest)


# --------------------------------------------------
# Experiment tracking integration

def create_experiment(
    root: str,
    experiment_id: str,
    name: str,
    description: str,
    config: Dict[str, Any],
    dataset_hash: str,
    tokenizer_checksum: str,
    seed: int,
    tags: Optional[List[str]] = None
) -> ExperimentManifest:
    """Create a new experiment manifest."""
    manifest = ExperimentManifest(
        experiment_id=experiment_id,
        name=name,
        description=description,
        created_at=_utcnow(),
        config=config,
        dataset_hash=dataset_hash,
        tokenizer_checksum=tokenizer_checksum,
        seed=seed,
        tags=tags or [],
        checkpoints=[],
        lineage_root=""
    )
    save_experiment_manifest(root, manifest)
    return manifest


def finalize_experiment(root: str, experiment_id: str, metrics: Dict[str, Any]) -> Optional[ExperimentManifest]:
    """Finalize experiment with final metrics."""
    manifest = load_experiment_manifest(root, experiment_id)
    if manifest:
        manifest.metrics = metrics
        save_experiment_manifest(root, manifest)
    return manifest
