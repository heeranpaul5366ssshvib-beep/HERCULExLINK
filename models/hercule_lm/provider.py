from __future__ import annotations
"""HERCULE-LM inference provider (N3 §24): same adapter contract.

Wraps a trained (or random-control) checkpoint + its tokenizer behind
generate/chat/health/metadata. Pure local NumPy inference; no
network, no Ollama, no pretrained weights. Registered lazily by
ModelManager-style callers; never executes tools or touches policy.
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.adapters.base_adapter import BaseAdapter


class HerculeLMUnavailable(RuntimeError):
    pass


class HerculeLMProvider(BaseAdapter):
    """Local HERCULE-LM checkpoint behind the standard adapter contract."""

    name = "hercule-lm"

    def __init__(self, checkpoint: str = "", tokenizer_dir: str = ""):
        self._checkpoint = str(checkpoint or "")
        self._tokenizer_dir = str(tokenizer_dir or "")
        self._model = None
        self._tokenizer = None
        self._manifest: Dict[str, Any] = {}
        self._load_ms = 0.0

    # --------------------------------------------------
    def _ensure_loaded(self):
        if self._model is not None:
            return self._model
        from . import checkpoint as ckpt
        from .config import HerculeLMConfig
        from .model import HerculeLM
        from .tokenizer import HerculeBPETokenizer

        if not self._checkpoint:
            raise HerculeLMUnavailable("no HERCULE-LM checkpoint configured")
        manifest = json_load(Path(self._checkpoint) / "manifest.json")
        config = HerculeLMConfig.from_dict(manifest["architecture"])
        tok_dir = self._tokenizer_dir or f"training/tokenizer/{config.tokenizer_id}"
        tokenizer = HerculeBPETokenizer.load(tok_dir)
        model = HerculeLM(config, seed=0)
        ckpt.load_checkpoint(self._checkpoint, model, strict=True)
        self._tokenizer, self._model = tokenizer, model
        self._manifest = manifest
        return model

    def health(self) -> Dict[str, Any]:
        try:
            # If a specific checkpoint is configured, validate it directly
            if self._checkpoint:
                checkpoint_path = Path(self._checkpoint)
                manifest_path = checkpoint_path / "manifest.json"
                weights_path = checkpoint_path / "weights.npz"
                
                if not manifest_path.exists() or not weights_path.exists():
                    return {"status": "unavailable", "available": False,
                            "reason": f"checkpoint not found: {self._checkpoint}", 
                            "native": True, "provider": "hercule-lm"}
                
                try:
                    import json
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if "random initialization" not in manifest.get("origin", ""):
                        return {"status": "unavailable", "available": False,
                                "reason": "not a HERCULE-LM checkpoint", 
                                "native": True, "provider": "hercule-lm"}
                except Exception:
                    return {"status": "unavailable", "available": False,
                            "reason": "invalid checkpoint manifest", 
                            "native": True, "provider": "hercule-lm"}
                
                # Checkpoint exists and is valid
                if self._model is not None:
                    return {"status": "healthy", "available": True, "provider": "hercule-lm",
                            "model": self._manifest.get("model_id", ""),
                            "params": self._manifest.get("parameter_count", 0),
                            "checkpoint": self._checkpoint,
                            "tokenizer": self._manifest.get("tokenizer", {}).get("checksum", ""),
                            "architecture_hash": self._manifest.get("architecture_hash", ""),
                            "capabilities": ["chat", "generation"],
                            "native": True}
                
                # Valid checkpoint but model not loaded yet (lazy loading)
                return {"status": "healthy", "available": True, "provider": "hercule-lm",
                        "model": manifest.get("model_id", ""),
                        "params": manifest.get("parameter_count", 0),
                        "checkpoint": self._checkpoint,
                        "capabilities": ["chat", "generation"],
                        "native": True}
            
            # No specific checkpoint configured - discover available models
            models = self.discover_models()
            if not models:
                return {"status": "unavailable", "available": False,
                        "reason": "no HERCULE-LM checkpoints found", "native": True, "provider": "hercule-lm"}
            
            # If we have a loaded model, return its details
            if self._model is not None:
                return {"status": "healthy", "available": True, "provider": "hercule-lm",
                        "model": self._manifest.get("model_id", ""),
                        "params": self._manifest.get("parameter_count", 0),
                        "checkpoint": self._checkpoint,
                        "tokenizer": self._manifest.get("tokenizer", {}).get("checksum", ""),
                        "architecture_hash": self._manifest.get("architecture_hash", ""),
                        "capabilities": ["chat", "generation"],
                        "native": True}
            
            # Provider is available but no model loaded yet (lazy loading)
            return {"status": "healthy", "available": True, "provider": "hercule-lm",
                    "model": models[0] if models else "",
                    "params": 0,
                    "checkpoint": None,
                    "discovered_models": models,
                    "capabilities": ["chat", "generation"],
                    "native": True}
        except Exception as exc:
            return {"status": "unavailable", "available": False,
                    "reason": str(exc)[:200], "native": True, "provider": "hercule-lm"}

    def metadata(self) -> Dict[str, Any]:
        return {"provider": "hercule-lm", "manifest": dict(self._manifest)}

    def discover_models(self) -> List[str]:
        """Discover installed HERCULE-LM checkpoints (valid manifest + weights)."""
        from . import checkpoint as ckpt
        from .config import HerculeLMConfig

        checkpoints_root = Path("training/checkpoints")
        if not checkpoints_root.exists():
            return []
        models = []
        for run_dir in checkpoints_root.iterdir():
            if not run_dir.is_dir():
                continue
            for step_dir in run_dir.iterdir():
                if not step_dir.is_dir() or not step_dir.name.startswith("step_"):
                    continue
                manifest_path = step_dir / "manifest.json"
                weights_path = step_dir / "weights.npz"
                if not manifest_path.exists() or not weights_path.exists():
                    continue
                try:
                    import json
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if "random initialization" not in manifest.get("origin", ""):
                        continue
                    model_id = manifest.get("model_id", step_dir.name)
                    if model_id not in models:
                        models.append(model_id)
                except Exception:
                    continue
        return models

    def load_model(self, model: str = "") -> Dict[str, Any]:
        """Load/switch to a specific HERCULE-LM checkpoint by model_id."""
        from . import checkpoint as ckpt
        from .config import HerculeLMConfig
        from .model import HerculeLM
        from .tokenizer import HerculeBPETokenizer
        import json

        checkpoints_root = Path("training/checkpoints")
        candidates = []
        if model:
            # Find all checkpoints by model_id
            for run_dir in checkpoints_root.iterdir():
                if not run_dir.is_dir():
                    continue
                for step_dir in run_dir.iterdir():
                    if not step_dir.is_dir() or not step_dir.name.startswith("step_"):
                        continue
                    manifest_path = step_dir / "manifest.json"
                    if not manifest_path.exists():
                        continue
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        if manifest.get("model_id") == model:
                            if (step_dir / "weights.npz").exists():
                                # Extract step number from directory name
                                step_str = step_dir.name.replace("step_", "")
                                try:
                                    step_num = int(step_str)
                                    candidates.append((step_num, str(step_dir), manifest))
                                except ValueError:
                                    candidates.append((0, str(step_dir), manifest))
                    except Exception:
                        continue
            if candidates:
                # Pick the checkpoint with the highest step number
                candidates.sort(key=lambda x: x[0], reverse=True)
                target_checkpoint = candidates[0][1]
            else:
                raise HerculeLMUnavailable(f"no HERCULE-LM checkpoint found for model: {model}")
        else:
            # Use latest.json if available
            latest = ckpt.read_latest(str(checkpoints_root))
            if latest:
                target_checkpoint = latest
            else:
                raise HerculeLMUnavailable("no HERCULE-LM checkpoint found for latest")

        if not target_checkpoint:
            raise HerculeLMUnavailable(f"no HERCULE-LM checkpoint found for model: {model or 'latest'}")

        # Load the checkpoint
        manifest = json.loads((Path(target_checkpoint) / "manifest.json").read_text(encoding="utf-8"))
        config = HerculeLMConfig.from_dict(manifest["architecture"])
        tok_dir = self._tokenizer_dir or f"training/tokenizer/{config.tokenizer_id}"
        tokenizer = HerculeBPETokenizer.load(tok_dir)
        new_model = HerculeLM(config, seed=0)
        ckpt.load_checkpoint(target_checkpoint, new_model, strict=True)

        self._checkpoint = target_checkpoint
        self._model = new_model
        self._tokenizer = tokenizer
        self._manifest = manifest

        return {"status": "loaded", "model": model or manifest.get("model_id", ""),
                "checkpoint": target_checkpoint, "params": manifest.get("parameter_count", 0)}

    def embeddings(self, model: str, text: str):
        raise HerculeLMUnavailable("HERCULE-LM has no embedding model")

    def score(self, prompt: str, completion: str) -> float:
        """Mean log-probability of a completion (ranking aid only)."""
        self._ensure_loaded()
        assert self._model is not None and self._tokenizer is not None
        return float(self._model.score(
            self._tokenizer.encode(str(prompt or "")),
            self._tokenizer.encode(str(completion or ""))))

    def generate(self, prompt: str, model: Optional[str] = None,
                 system: str = "", timeout_s: Optional[float] = None,
                 **kwargs: Any) -> str:
        started = time.perf_counter()
        budget = float(timeout_s or 120.0)
        self._ensure_loaded()
        assert self._model is not None and self._tokenizer is not None
        start_ids = self._tokenizer.encode(str(prompt or ""))
        out = self._model.generate(
            start_ids,
            max_new_tokens=int(kwargs.get("max_tokens", kwargs.get("max_new_tokens", 64))),
            temperature=float(kwargs.get("temperature", 0.0)),
            seed=int(kwargs.get("seed", 0)))
        elapsed = time.perf_counter() - started
        if elapsed > budget:
            raise HerculeLMUnavailable(f"generation exceeded {budget:.0f}s budget")
        text = self._tokenizer.decode(out)
        # Return only the continuation (never echo bookkeeping).
        return text[len(str(prompt or "")):] if text.startswith(str(prompt or "")) else text

    def chat(self, model: Optional[str] = None, prompt: str = "",
             system: str = "", messages: Optional[List[Dict[str, Any]]] = None,
             timeout_s: Optional[float] = None, **kwargs: Any) -> str:
        if messages:
            prompt = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}"
                               for m in messages if isinstance(m, dict))
        if system:
            prompt = f"{system}\n{prompt}"
        return self.generate(prompt, model=model, system="",
                             timeout_s=timeout_s, **kwargs)


def json_load(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
