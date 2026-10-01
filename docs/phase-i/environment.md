# Environment, Installation, Troubleshooting

## Install

Requires Python >= 3.11 (verified on 3.14.6, Windows amd64).

Portable floors (any platform):

```
pip install -r requirements.txt
```

Exact verified set (this machine):

```
pip install -r requirements-lock.txt
```

`requirements-lock.txt` is platform-specific (faiss-cpu/torch wheels
differ per OS/CPU/CUDA). Regenerate per platform with
`pip freeze --exclude-editable`. Do not pretend one lock works
everywhere — floors stay portable, locks stay per-platform.

## Model weights

Production embeddings need `sentence-transformers/all-MiniLM-L6-v2`
(~90MB, cached after first load). Prefetch while online:

```
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

Offline runs use the HF cache only (`HF_HUB_OFFLINE=1` is forced in
`tests/conftest.py`; missing weights skip live tests honestly).

## Validate

```python
from system.config.env_validation import validate_environment
report = validate_environment(check_models=True)  # loads weights
report = validate_environment()                   # static only, fast
assert report["ok"]
```

Checks python floor, all required package floors, FAISS/memory vector
backends, embedding provider availability, devices, and static
embedding-config validity. Read-only: never installs.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `EMBEDDING_BACKEND_UNAVAILABLE` at startup | weights missing / server down | prefetch model or set fallback / offline mode |
| `EMBEDDING_TEST_PROVIDER_BLOCKED` | hash configured for production | use production provider or non-production mode |
| `EMBEDDING_INDEX_INCOMPATIBLE` | index built by another model/dim | re-ingest with active provider or restore matching index |
| `EMBEDDING_DIMENSION_MISMATCH` | mixed-dim vectors | check `index_descriptor()` for mixed models |
| live tests skip | no cached weights / offline | prefetch (above) or accept hash-leg coverage |
| slow first test | transformer weight load (~10s) | one-time per session (module fixtures share it) |
