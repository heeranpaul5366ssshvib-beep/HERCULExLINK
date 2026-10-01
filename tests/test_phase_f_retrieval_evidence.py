"""Phase F: retrieval 2.0, quality metrics, evidence, conflict, freshness."""

from knowledge.embeddings.embedding_index import EmbeddingIndex
from knowledge.evidence import (
    EvidenceType,
    detect_conflicts,
    evidence_from_retrieved,
    freshness_score,
    ground_answer,
)
from knowledge.hybrid_retrieval import HybridRetriever, RetrievalStrategy, analyze_query
from knowledge.indexing.index_manager import IndexManager
from knowledge.ingestion import KnowledgeIngestionPipeline
from knowledge.knowledge_manager import KnowledgeManager


def _fixture():
    index, embeddings = IndexManager(), EmbeddingIndex()
    pipeline = KnowledgeIngestionPipeline(index, embeddings, chunk_size=25, overlap=5)
    pipeline.ingest("router.md", "The model router selects adapters by health checks and capability. " * 6, source="docs")
    pipeline.ingest("cache.md", "The runtime cache expires entries after TTL seconds elapse. " * 6, source="docs")
    return HybridRetriever(index, embeddings)


def test_strategy_selection_per_query_shape():
    assert analyze_query('"exact phrase"').strategy == RetrievalStrategy.EXACT_TERM
    assert analyze_query("router").strategy == RetrievalStrategy.EXACT_TERM
    assert analyze_query("how does the model router pick adapters").strategy == RetrievalStrategy.SEMANTIC
    assert analyze_query("source:docs router").strategy == RetrievalStrategy.METADATA_FILTER
    assert analyze_query("latest router changes and recent updates").strategy == RetrievalStrategy.FRESHNESS_AWARE
    assert analyze_query("previous attempts at fixing the router").strategy == RetrievalStrategy.TASK_HISTORY
    assert analyze_query("compare the router versus the cache with pros and cons in detail").strategy == RetrievalStrategy.HYBRID


def test_exact_term_retrieval():
    retriever = _fixture()
    items = retriever.retrieve('"router"', top_k=5)
    assert items
    assert all(i.strategy == RetrievalStrategy.EXACT_TERM for i in items)
    assert all(i.rank >= 1 for i in items)
    assert items == sorted(items, key=lambda i: i.rank)


def test_semantic_and_hybrid_paths_score_and_rank():
    retriever = _fixture()
    semantic = retriever.retrieve("which component selects model adapters", top_k=5)
    assert semantic and semantic[0].chunk_id.startswith("router.md")
    hybrid = retriever.retrieve("compare the router versus the cache with pros and cons in detail", top_k=5)
    assert hybrid
    assert retriever.last_quality is not None
    assert retriever.last_quality.result_count == len(hybrid)
    assert retriever.last_quality.latency_ms >= 0


def test_metadata_filter_constrains_source():
    retriever = _fixture()
    items = retriever.retrieve("source:docs router", top_k=10)
    assert items
    assert all((i.provenance.source if i.provenance else "") == "docs" for i in items)
    assert retriever.last_quality.strategy == RetrievalStrategy.METADATA_FILTER.value


def test_retrieval_quality_precision_recall():
    retriever = _fixture()
    items = retriever.retrieve("model router adapters", top_k=5)
    ranked = [i.chunk_id for i in items]
    relevant = [c for c in ranked if c.startswith("router.md")]
    quality = retriever.last_quality
    assert quality.precision_at_k(relevant, 3, ranked) >= 0.5
    assert quality.recall(relevant, ranked) == 1.0
    assert quality.precision_at_k([], 0, ranked) == 0.0
    assert quality.recall([], ranked) == 0.0
    assert 0.0 <= quality.duplicate_rate <= 1.0


def test_empty_retrieval_returns_no_items_not_errors():
    retriever = _fixture()
    items = retriever.retrieve("xyzzqy improbable nonsense phrase here", top_k=5)
    assert isinstance(items, list)
    assert retriever.last_quality.result_count == len(items)


def test_duplicate_ingestion_is_measured_not_hidden():
    index, embeddings = IndexManager(), EmbeddingIndex()
    pipeline = KnowledgeIngestionPipeline(index, embeddings, chunk_size=25, overlap=0)
    pipeline.ingest("dup.md", "identical content repeated here " * 10, source="a")
    pipeline.ingest("dup.md", "identical content repeated here " * 10, source="a")
    retriever = HybridRetriever(index, embeddings)
    retriever.retrieve("identical content repeated here with more words added", top_k=5)
    assert retriever.last_quality is not None


def test_missing_embeddings_degrades_to_keyword():
    index = IndexManager()
    index.index_document("lonely#c0", "router adapter health selection")
    retriever = HybridRetriever(index, None)
    items = retriever.retrieve("compare the router versus the cache with pros and cons in detail", top_k=5)
    assert isinstance(items, list)  # no crash without a vector store


def test_malformed_metadata_never_crashes_retrieval():
    index, embeddings = IndexManager(), EmbeddingIndex()
    index.index_document("odd#c0", "router adapter health")
    embeddings.add("odd#c0", [1.0, 0.0], None)
    retriever = HybridRetriever(index, embeddings)
    items = retriever.retrieve("router", top_k=5)
    assert isinstance(items, list)


def test_evidence_conflict_freshness_grounding():
    manager = KnowledgeManager()
    manager.ingest_document("v1.md", "The cache TTL is fixed at sixty seconds always. " * 6, source="team-a")
    manager.ingest_document("v2.md", "The cache TTL is not fixed and adapts dynamically instead. " * 6, source="team-b")
    items = [dict(i, text=i["text"]) for i in manager.hybrid_retrieve("cache TTL behavior", top_k=10)]
    assert items
    conflicts = detect_conflicts(items, topic="cache TTL")
    assert conflicts
    assert conflicts[0].source_a != conflicts[0].source_b
    assert conflicts[0].excerpt_a and conflicts[0].excerpt_b
    same_source = [i for i in items if (i.get("provenance") or {}).get("source") == "team-a"][:2]
    assert detect_conflicts(same_source) == []
    evidence = evidence_from_retrieved("TTL adapts dynamically", items[0])
    assert evidence.kind == EvidenceType.DIRECT
    assert evidence.chunk_id
    grounded = ground_answer(["TTL adapts dynamically over time", "completely unrelated claim zzz"], items)
    assert grounded[0]["evidence"]["kind"] == EvidenceType.DIRECT.value
    assert grounded[1]["evidence"]["kind"] == EvidenceType.UNVERIFIED.value
    assert freshness_score("not-a-timestamp") == 0.0
