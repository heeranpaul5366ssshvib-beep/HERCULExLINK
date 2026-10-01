#!/usr/bin/env python3
"""Persistent artifact manifest (Phase 5L): sha256 for every report.

Reports are the durable evidence layer (GPU boxes may have ephemeral
scratch). This manifest lets any later session verify artifact
integrity. Run after generating reports.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports" / "frontier_program"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    entries = []
    for path in sorted(REPORTS.glob("*.json")):
        if path.name == "MANIFEST.json":
            continue
        entries.append({"file": path.name, "bytes": path.stat().st_size,
                        "sha256": _sha(path)})
    for path in sorted(REPORTS.glob("*.md")):
        entries.append({"file": path.name, "bytes": path.stat().st_size,
                        "sha256": _sha(path)})
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "artifacts": entries, "count": len(entries)}
    (REPORTS / "MANIFEST.json").write_text(json.dumps(manifest, indent=1),
                                           encoding="utf-8")
    print(f"manifest: {len(entries)} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
