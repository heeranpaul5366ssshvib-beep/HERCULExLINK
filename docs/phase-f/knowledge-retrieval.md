# Knowledge & Retrieval 2.0

## Ingestion (`knowledge/ingestion.py`)

`INPUT → IDENTIFY TYPE → PARSE → NORMALIZE → CHUNK → METADATA →
EMBEDDING → INDEX → PROVENANCE`

- `identify_content_type` from document-id suffix (md/txt/pdf/docx/html/json).
- `normalize_text` collapses whitespace; `chunk_text` word-windows with
  overlap and deterministic `doc_id#cN` chunk ids.
- `KnowledgeIngestionPipeline` writes the existing `IndexManager`
  (keyword), `EmbeddingIndex` (vector + metadata + provenance) and
  `Ontology` (document concept). Partial failures are collected in
  `IngestionResult.errors`, never raised midway.
- Embedding fn is injectable (`Callable[[str], List[float]]`); default
  `hash_embed` is deterministic test-grade (see ADR-003).

## Provenance (`knowledge/provenance.py`)

Every chunk carries source, origin, document/chunk id, content type,
version, aware `indexed_at`, transformation chain, and direct/inferred
flag. `parse_timestamp` tolerates legacy naive strings as UTC so old
persisted data never causes naive/aware `TypeError`.

## Hybrid retrieval (`knowledge/hybrid_retrieval.py`)

Strategy selection (`analyze_query`) is rule-based and deterministic:

| Query shape | Strategy |
|---|---|
| quoted / single token | `exact_term` (keyword index) |
| `key:value` tokens | `metadata_filter` (provenance fields) |
| latest/recent/… | `freshness_aware` (+recency boost) |
| previous/attempted/history/… | `task_history` (caller also pulls Experience) |
| compare/research/long | `hybrid` (0.4 lexical + 0.6 semantic) |
| default | `semantic` (cosine over embedding index, FAISS backend when provided) |

Fusion dedups by chunk id, ranks, and records `RetrievalQuality`:
latency, candidates, duplicate rate (multi-path hits), score spread,
plus `precision_at_k`/`recall` against relevance judgments.

## Evidence (`knowledge/evidence.py`)

- `Evidence` kinds: DIRECT / INFERRED / ASSUMED / UNVERIFIED / CONTRADICTED.
- `detect_conflicts` preserves both excerpts + fresher source instead of
  merging contradictions (negation-signal heuristic, documented limits).
- `freshness_score` linear decay to TTL; `ground_answer` attaches best
  supporting chunk per statement, UNVERIFIED when nothing supports it.
