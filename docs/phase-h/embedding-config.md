# Embedding Configuration Reference

## Modes

| Mode | Provider default | Test backends | Trigger |
|---|---|---|---|
| production | sentence-transformers/MiniLM | BLOCKED (fail closed) | default, `HERCULE_MODE=production` |
| test | hash (deterministic) | allowed | `HERCULE_MODE=test` |
| ci | hash, forced over any config | allowed | `HERCULE_MODE=ci` |
| offline | sentence-transformers, hash fallback | allowed as fallback | `HERCULE_MODE=offline` |
| simulation | hash | allowed | `HERCULE_MODE=simulation` |

## Environment variables

`HERCULE_MODE`, `HERCULE_EMBEDDING_PROVIDER`, `HERCULE_EMBEDDING_MODEL`,
`HERCULE_EMBEDDING_DIMENSION`, `HERCULE_EMBEDDING_DEVICE`,
`HERCULE_EMBEDDING_BATCH_SIZE`, `HERCULE_EMBEDDING_FALLBACK`,
`HERCULE_EMBEDDING_FALLBACK_MODEL`. Explicit dict arguments beat env;
env beats mode defaults; `ci` mode always forces hash.

## Examples

Production (default, nothing to set):
`provider=sentence-transformers model=sentence-transformers/all-MiniLM-L6-v2 device=cpu`

Hermetic CI: `HERCULE_MODE=ci` (hash forced even if configured otherwise).

Offline with fallback:
`HERCULE_MODE=offline HERCULE_EMBEDDING_FALLBACK=hash`
→ cached MiniLM when loadable, else hash with `fallback_used: true`
in the resolution report; unconfigured fallback fails clearly.

## Validation (startup)

Unknown provider, empty model, bad device (`cpu|auto|cuda*|mps*|
ollama-server`), dimension/normalization mismatch, test-only backend
in production, and unhealthy backends are all rejected with coded
`EmbeddingConfigError`s. Config *errors* fail fast (fallback cannot
fix a typo); only *unavailability* falls through to the fallback.

## Device selection

`cpu` default; `auto` defers to the provider; `cuda[:N]`/`mps[:N]` for
accelerators; `ollama-server` for remote inference. Unknown devices
are rejected, never ignored.

## Index compatibility

Every `EmbeddingIndex` carries `{provider, model_id, dimension,
normalized, version}` (`write_index_metadata`); `VectorMemory`
manifests carry the same. `check_index_compatibility` /
`restore(..., expected=...)` reject model/dimension/normalization
mismatches with `EMBEDDING_INDEX_INCOMPATIBLE`; absent fields keep
old manifests loadable. Mixed-model indexes are rejected at
`index_descriptor()` time.
