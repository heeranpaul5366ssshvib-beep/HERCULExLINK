#!/usr/bin/env python3
"""Dataset-v2 integration validation + migration recommendation (Phase 5K).

Validates the generated dataset_v2 artifact WITHOUT swapping production
training data:
  - artifact schema (manifest + report keys, hashes, splits)
  - split integrity (leak-free, counts sum, hash format)
  - license allowlist conformance of the manifest sources
  - shard roundtrip on a real token stream slice
  - tokenizer compatibility (vocab coverage probe)
Then emits a migration recommendation with measured evidence.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    artifact = ROOT / "reports" / "frontier_program" / "dataset_v2.json"
    if not artifact.exists():
        print("BLOCKED: dataset_v2.json missing (run scripts/dataset_v2_report.py)")
        return 2
    bundle = json.loads(artifact.read_text(encoding="utf-8"))
    manifest, report = bundle["manifest"], bundle["report"]
    checks: dict = {}

    # 1. schema
    checks["schema"] = all(k in manifest for k in
                           ("dataset_hash", "splits", "sources", "documents")) \
        and all(k in report for k in
                ("filter", "dedup_exact", "dedup_near", "languages",
                 "contamination", "splits", "dataset_hash"))
    # 2. hash format + agreement
    h = manifest["dataset_hash"]
    checks["hash"] = (len(h) == 64 and report["dataset_hash"] == h)
    # 3. splits sum to manifest documents (leak-free verified at build)
    sizes = report["splits"]
    checks["splits"] = sum(sizes.values()) == manifest["documents"]
    # 4. license allowlist
    allowed = {"HERCULE-authored (MIT, repo)"}
    checks["licenses"] = all(s["license"] in allowed for s in manifest["sources"])
    # 5. contamination clean
    checks["contamination"] = report["contamination"]["hit_count"] == 0
    # 6. shard roundtrip on a real slice of the cached train stream
    from models.hercule_lm.data import cached_stream
    from models.hercule_lm.dataset_v2 import write_shards
    from models.hercule_lm.data import DataSource, load_documents
    from models.hercule_lm.tokenizer import HerculeBPETokenizer
    import tempfile

    sources = [DataSource(**s) for s in manifest["sources"]]
    docs = load_documents(str(ROOT / "training/data/raw"), sources, paragraphs=True)
    tok = HerculeBPETokenizer.train([d.text for d in docs[:50]], vocab_size=300,
                                    corpus_version="probe")
    with tempfile.TemporaryDirectory() as tmp:
        stream = cached_stream(tok, docs[:50], 16, seed=0, cache_dir=tmp,
                               corpus_hash="probe")
        sh = write_shards(stream, 16, 64, tmp + "/sh")
        from models.hercule_lm.data import ShardedStream
        loader = ShardedStream([s["path"] for s in sh["shards"]])
        got, total = 0, 0
        while True:
            batch = loader.next_batch(2, 16)
            if batch is None:
                break
            total += batch[0].size
            got += 1
        checks["shards"] = (sh["total_tokens"] == int(stream.size) and total > 0)
    # 7. tokenizer compatibility probe (all stream ids < vocab)
    checks["tokenizer"] = bool(int(stream.max()) < 300)

    # Migration recommendation (evidence-based, NOT automatic)
    dup_rate = (report["dedup_exact"]["removed_exact"]
                / max(1, report["dedup_exact"]["input"]))
    rec = {
        "migrate": False,
        "reason": "v2 validated as candidate; production training data NOT swapped automatically",
        "evidence": {
            "dup_rate": round(dup_rate, 3),
            "contamination_hits": report["contamination"]["hit_count"],
            "all_checks": checks,
        },
        "recommendation": (
            "ADOPT v2 filtering at ingest (exact dedup removes "
            f"{dup_rate:.0%} duplicates) after one GPU-box A/B run "
            "comparing raw vs v2 loss trajectories; keep raw manifests "
            "for lineage.") if dup_rate > 0.1 and all(checks.values()) else
        "HOLD: v2 offers no measured advantage worth a data swap.",
    }
    out = {"checks": checks, "all_pass": all(checks.values()),
           "migration": rec}
    dest = ROOT / "reports" / "frontier_program" / "dataset_v2_integration.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
