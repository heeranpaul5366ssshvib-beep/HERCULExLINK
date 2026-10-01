# Retrieval Benchmarks (measured, not invented)

Dataset: `knowledge/datasets/phase_g_retrieval.json` (7 docs, 8 queries:
exact, semantic, paraphrase, metadata-filter, freshness, duplicate,
conflict, task-history — each with doc-level relevance judgments).
Runner: `scripts/benchmark_retrieval.py` → report
`data/benchmarks/phase_g_retrieval.json`.

## Provider comparison (final run)

| Provider | Dim | Ingest | Single | Batch (7 texts) | P@3 | Recall | MRR |
|---|---|---|---|---|---|---|---|
| hash (test-grade) | 64 | ~2ms | ~0.2ms | ~1ms (~7k/s) | 0.58 | 1.0 | 0.85 |
| sentence-transformers MiniLM | 384 | ~310ms | ~46ms | ~227ms (~31/s) | 0.63 | 1.0 | **1.0** |

One-time model load ~10s (cold), cached afterwards. Live leg ranks the
correct document first on every semantic/paraphrase/freshness/history
query; freshness boost promotes the newer TTL version; conflicting
sources stay distinguishable with both excerpts preserved.

## Fusion-weight grid (hash provider, deterministic)

| kw/vw | P@3 | R | MRR |
|---|---|---|---|
| 1.0/0.0 | 0.625 | 1.0 | 0.938 |
| 0.6/0.4 | 0.625 | 1.0 | 1.0 |
| 0.4/0.6 (shipped default) | 0.583 | 1.0 | 0.854 |
| 0.2/0.8 | 0.583 | 1.0 | 0.833 |
| 0.0/1.0 | 0.583 | 0.938 | 0.833 |

Decision: keep 0.4/0.6. The grid runs on hash vectors, which are
lexically correlated by construction and understate semantic value;
the live leg (MRR 1.0 at 0.4/0.6) confirms the default is sound with
real embeddings. Re-run the grid after wiring a stronger embedder
before changing the default.

## Before/after (hash → real embeddings)

- Query latency: vector path ~0.1ms → ~5–50ms per query embedding
  (batch amortized); lexical path unchanged.
- Quality: MRR 0.85 → 1.0; paraphrase queries resolve correctly.
- Memory/index: 6× wider vectors (64→384 floats); FAISS IP index +
  JSON records persist/restore verified on both backends.
