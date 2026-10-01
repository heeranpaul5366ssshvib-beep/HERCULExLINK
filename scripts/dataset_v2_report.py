#!/usr/bin/env python3
"""Generate the Phase 4I dataset quality report on the real seed corpus."""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.hercule_lm.data import DataSource, load_documents
from models.hercule_lm.dataset_v2 import (build_dataset, filter_near_duplicates,
                                          language_distribution)


def main() -> int:
    t0 = time.perf_counter()
    sources_raw = json.loads((ROOT / "training/data/sources.json").read_text(encoding="utf-8"))
    sources = [DataSource(**s) for s in sources_raw]
    docs = load_documents(str(ROOT / "training/data/raw"), sources, paragraphs=True)
    out = build_dataset("hercule-seed", "v2", sources, docs,
                        allowed_licenses=["HERCULE-authored (MIT, repo)"])
    # Documented near-dup sample (full-corpus O(n^2) exceeds the cap).
    sample = out["docs"][:500]
    _, near_sample = filter_near_duplicates(sample, threshold=0.8, cap=2000)
    report = out["report"]
    report["near_dup_sample"] = {"sample_n": len(sample), **near_sample}
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["wall_seconds"] = round(time.perf_counter() - t0, 1)
    report["tokenizer_note"] = "tokenizer unchanged (checksum-gated cache in train.py)"
    dest = ROOT / "reports" / "frontier_program"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "dataset_v2.json").write_text(json.dumps({
        "manifest": out["manifest"], "report": report}, indent=1), encoding="utf-8")
    print(f"docs={len(out['docs'])} hash={out['manifest']['dataset_hash']}")
    print(f"languages={report['languages']['by_language']}")
    print(f"score mean={report['score_hist']['mean']} "
          f"lt0.5={report['score_hist']['lt_0_5']} ge0.8={report['score_hist']['ge_0_8']}")
    print(f"contamination hits={report['contamination']['hit_count']}")
    print(f"near-dup sample(500): removed={near_sample['removed_near']} "
          f"groups={near_sample.get('groups', 0)}")
    print(f"splits={report['splits']} wall={report['wall_seconds']}s")
    print("written to reports/frontier_program/dataset_v2.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
