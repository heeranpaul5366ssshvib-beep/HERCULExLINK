from __future__ import annotations
"""Reproducible remote bundle builder (spec §2).

Copies ONLY allowlisted paths; refuses secrets; writes
BUNDLE_MANIFEST.json with per-file hashes + run parameters.
"""

import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.kaggle_trainer import manifest as _man

# Allowlist: relative paths (files or dirs) copied into the bundle.
ALLOW = (
    "models/hercule_lm",
    "models/adapters/base_adapter.py",
    "training/data/raw",
    "training/data/sources.json",
    "training/data/overfit",
    "evaluation",
    "scripts/gpu_auto_run.py",
)

EXCLUDE_DIRS = {".venv", "__pycache__", ".git", ".pytest_cache",
                "node_modules", "dist", "build", "__MACOSX"}
EXCLUDE_FILES = {".env", "kaggle.json"}
# Match standalone secret tokens (tokenizer.py must NOT match).
SECRET_NAME_RE = re.compile(r"(^|[_.\-])(key|token|secret|credential|passwd|kaggle\.json|env)([_.\-]|$)", re.I)
SECRET_CONTENT_RE = re.compile(
    r"(kaggle[^a-z0-9]{0,8}key|api[_-]?key\s*[:=])", re.I)


def _secret_scan(path: Path, rel: str) -> Optional[str]:
    if path.name in EXCLUDE_FILES or SECRET_NAME_RE.search(path.name):
        return f"secret-like filename: {rel}"
    if path.suffix in {".py", ".json", ".md", ".txt", ".yaml", ".yml", ".cfg"}:
        try:
            text = path.read_text(encoding="utf-8", errors="strict")[:200000]
        except (OSError, UnicodeDecodeError):
            return None
        if SECRET_CONTENT_RE.search(text):
            return f"secret-like content: {rel}"
    return None


def collect_files(root: Path) -> List[str]:
    rels: List[str] = []
    for item in ALLOW:
        src = root / item
        if not src.exists():
            continue
        if src.is_file():
            rels.append(item)
            continue
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
                continue
            if path.suffix == ".pyc":
                continue
            rels.append(rel)
    return sorted(set(rels))


def build_bundle(root: str = "", dest: str = "", params: Dict[str, Any] | None = None,
                 extra_files: List[str] | None = None) -> Dict[str, Any]:
    """Build bundle dir; returns manifest dict. Raises on secrets."""
    from tools.kaggle_trainer.discover import find_root

    base = Path(root) if root else find_root()
    out = Path(dest) if dest else base / "artifacts" / "kaggle_bundle"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    params = dict(params or {})
    rels = collect_files(base)
    for extra in extra_files or []:
        if (base / extra).is_file():
            rels.append(extra)
    rels = sorted(set(rels))
    # Secret gate BEFORE any copy.
    for rel in rels:
        hit = _secret_scan(base / rel, rel)
        if hit:
            raise ValueError(f"BUNDLE_REFUSED: {hit}")
    entries = []
    for rel in rels:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base / rel, target)
        entries.append({"path": rel, "bytes": target.stat().st_size,
                        "sha256": _man.sha_file(target)})
    bundle_manifest = {
        "format": "hercule-kaggle-bundle-v1",
        "params": params,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "files": entries,
        "bundle_hash": _man.sha_dir(out, [e["path"] for e in entries]),
    }
    _man.write_json(out / "BUNDLE_MANIFEST.json", bundle_manifest)
    return {"bundle_dir": str(out), "files": len(entries),
            "bundle_hash": bundle_manifest["bundle_hash"],
            "manifest": bundle_manifest}
