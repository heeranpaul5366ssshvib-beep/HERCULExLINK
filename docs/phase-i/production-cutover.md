# Production Cutover (measured)

## Cutover behavior

- `RuntimeInitializer().initialize({"mode": "production"})` resolves
  MiniLM-L6-v2 (health-checked), builds the `embeddings` service, and
  records the resolution report. Verified live: 384-dim vectors.
- `{"mode": "ci"}` forces hash even against explicit config; default
  `initialize()` wires no embeddings service (unchanged path).
- Startup gate distinguishes configuration_error (bad provider/model/
  dim/device/normalization, test-only in production) from
  backend_unavailable (valid config, backend down) from runtime_failure.

## Benchmark rerun (post-cutover, configured production provider)

| | hash | MiniLM (production) |
|---|---|---|
| P@3 / Recall / MRR | 0.583 / 1.0 / 0.854 | **0.625 / 1.0 / 1.0** |
| ingest / single / batch-7 | ~2ms / ~0.2ms / ~1ms | ~720ms / ~120ms / ~480ms |

Identical quality to the Phase G baseline (no retrieval regression,
no weight changes — live MRR 1.0 at the shipped 0.4/0.6 default).
Latency ranges reflect cold-load/machine variance (one-time ~10s
weight load); no improvement claimed.

## Router authority

`select_embedding_model(task, router, manager)` routes capability =
EMBEDDING then requires a registered provider for the routed id;
`route_and_embed` executes through the manager with correlation
tracing. Managers never substitute backends.

## Cache safety (audited)

Keys bind content-hash + model id + version; dimension re-validated on
hit (drift evicts); `use_cache=False` disables cleanly; version bumps
isolate; per-model entries never cross. Traces record hit/miss +
latency with fingerprints only.
