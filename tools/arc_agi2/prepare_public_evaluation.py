"""Materialize official public evaluation only for the post-freeze run.

The sparse checkout is extended only after development is complete. This
script records filenames and hashes and does not parse or print task JSON.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from tools.arc_agi2.prepare_data import OFFICIAL_URL, PINNED_COMMIT


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(root: Path) -> dict:
    root = root.resolve()
    target_root = root / "data" / "arc_agi2" / "public_evaluation"
    if target_root.exists():
        raise FileExistsError("public evaluation files already materialized")
    freeze_path = root / "artifacts" / "arc_agi2" / "solver_freeze.json"
    if not freeze_path.is_file():
        raise RuntimeError("public evaluation may be fetched only after solver freeze")
    source = root / "data" / "arc_agi2" / "_official_source"
    remote = run("git", "remote", "get-url", "origin", cwd=source)
    if remote.rstrip("/").lower() != OFFICIAL_URL.lower():
        raise RuntimeError(f"unexpected ARC source remote: {remote}")
    commit = run("git", "rev-parse", "HEAD", cwd=source)
    if commit != PINNED_COMMIT:
        raise RuntimeError(f"official snapshot mismatch: {commit}")
    run("git", "sparse-checkout", "add", "data/evaluation", cwd=source)
    official = source / "data" / "evaluation"
    files = sorted(official.glob("*.json"))
    if len(files) != 120:
        raise RuntimeError(f"expected 120 official public evaluation tasks, found {len(files)}")
    target_root.mkdir(parents=True, exist_ok=False)
    rows = []
    for source_file in files:
        target = target_root / source_file.name
        shutil.copy2(source_file, target)
        rows.append({"file": target.name, "sha256": sha256(target)})
    manifest = {"source": OFFICIAL_URL, "source_commit": commit,
                "snapshot": "ARC-AGI-2 public evaluation (post-freeze only)",
                "materialized_utc": datetime.now(timezone.utc).isoformat(),
                "count": len(rows), "tasks": rows}
    (target_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"count": len(rows), "source_commit": commit,
            "manifest": str(target_root / "manifest.json")}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(prepare(args.root), indent=2))
