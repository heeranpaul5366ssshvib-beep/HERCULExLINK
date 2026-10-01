"""Phase F: knowledge ingestion pipeline + provenance."""

from datetime import datetime, timezone

from knowledge.ingestion import (
    KnowledgeIngestionPipeline,
    chunk_text,
    hash_embed,
    identify_content_type,
    normalize_text,
)
from knowledge.embeddings.embedding_index import EmbeddingIndex
from knowledge.indexing.index_manager import IndexManager
from knowledge.knowledge_manager import KnowledgeManager
from knowledge.ontology.ontology import Ontology
from knowledge.provenance import Provenance, parse_timestamp


def test_normalize_and_chunk_are_deterministic():
    raw = "  Hello\r\nworld   test one two three"
    assert normalize_text(raw) == "Hello world test one two three"
    chunks = chunk_text(" ".join(f"w{i}" for i in range(10)), chunk_size=4, overlap=1)
    assert chunks[0] == "w0 w1 w2 w3"
    assert chunks[1].startswith("w3 ")
    assert "".join(chunks).replace(" ", "").startswith("w0w1w2w3")
    assert chunk_text("") == []
    assert identify_content_type("guide.md", "x") == "text/markdown"
    assert identify_content_type("notes.txt", "x") == "text/plain"


def test_hash_embed_is_deterministic_and_normalized():
    a = hash_embed("model router health")
    b = hash_embed("model router health")
    assert a == b
    assert len(a) == 64
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9


def test_ingestion_pipeline_tracks_full_provenance():
    index, embeddings, ontology = IndexManager(), EmbeddingIndex(), Ontology()
    pipeline = KnowledgeIngestionPipeline(index, embeddings, ontology, chunk_size=20, overlap=5)
    result = pipeline.ingest("router.md", "The model router selects adapters by health. " * 10, source="unit-test", version="2")
    assert result.chunk_count >= 2
    assert result.errors == []
    assert result.content_type == "text/markdown"
    first = result.chunks[0]
    assert first.chunk_id == "router.md#c0"
    prov = first.provenance
    assert prov.source == "unit-test"
    assert prov.document_id == "router.md"
    assert prov.version == "2"
    assert prov.direct is True
    assert "chunk" in prov.transformation
    parsed = parse_timestamp(prov.indexed_at)
    assert parsed is not None and parsed.tzinfo is not None
    # Stores were populated.
    assert index.search("router")
    record = embeddings.get("router.md#c0")
    assert record and record["metadata"]["provenance"]["source"] == "unit-test"
    assert "router.md" in ontology.concepts()


def test_ingestion_rejects_empty_documents():
    pipeline = KnowledgeIngestionPipeline(IndexManager(), EmbeddingIndex())
    result = pipeline.ingest("empty.txt", "   \n  ")
    assert result.chunk_count == 0
    assert result.errors


def test_legacy_naive_timestamps_parse_as_utc():
    legacy = datetime(2024, 1, 2, 3, 4, 5).isoformat()  # naive, pre-Phase-E style
    parsed = parse_timestamp(legacy)
    assert parsed is not None and parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0
    aware = datetime.now(timezone.utc).isoformat()
    assert (parse_timestamp(aware) - parsed).total_seconds() > 0  # no TypeError
    assert parse_timestamp(None) is None
    assert parse_timestamp("not-a-timestamp") is None


def test_provenance_roundtrip_and_age():
    prov = Provenance(source="s", document_id="d", chunk_id="d#c0")
    clone = Provenance.from_dict(prov.as_dict())
    assert clone.source == "s" and clone.chunk_id == "d#c0"
    assert 0.0 <= prov.age_seconds() < 60.0


def test_knowledge_manager_ingest_and_health():
    manager = KnowledgeManager()
    result = manager.ingest_document("ops.txt", "Restart the adapter when health degrades. " * 8, source="unit-test")
    assert result.chunk_count >= 1
    health = manager.health()
    assert health["embeddings"] >= result.chunk_count
    assert health["indexed_words"] > 0
