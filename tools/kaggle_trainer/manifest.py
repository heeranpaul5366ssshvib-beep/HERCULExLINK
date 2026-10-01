from __future__ import annotations
"""Hashing + manifest helpers (spec §2). All hashes are sha256 hex."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha_dir(root: Path, rels: List[str]) -> str:
    digest = hashlib.sha256()
    for rel in sorted(rels):
        digest.update(rel.encode())
        digest.update(sha_file(root / rel).encode())
    return digest.hexdigest()


def write_json(path: Path, payload: Dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    tmp.replace(path)
    return str(path)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_bundle_manifest(bundle_dir: Path) -> Dict[str, Any]:
    """Re-hash every listed file; report mismatches (never assume)."""
    manifest = read_json(bundle_dir / "BUNDLE_MANIFEST.json")
    bad = []
    for entry in manifest.get("files", []):
        target = bundle_dir / entry["path"]
        if not target.exists() or sha_file(target) != entry["sha256"]:
            bad.append(entry["path"])
    return {"ok": not bad, "mismatched": bad,
            "files": len(manifest.get("files", []))}
