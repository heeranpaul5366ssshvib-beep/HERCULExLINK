from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Knowledge Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from knowledge.ontology.ontology import Ontology
from knowledge.indexing.index_manager import IndexManager
from knowledge.embeddings.embedding_index import EmbeddingIndex
from knowledge.retrieval.knowledge_retriever import KnowledgeRetriever
from knowledge.ingestion import KnowledgeIngestionPipeline
from knowledge.hybrid_retrieval import HybridRetriever, RetrievalStrategy


class KnowledgeManager:
    """
    ============================================
            HERCULE KNOWLEDGE MANAGER
    ============================================

    Central gateway for all knowledge systems.

    Coordinates:

    • Ontology
    • Document Indexing
    • Embeddings
    • Retrieval

    Future

    • Knowledge Graph
    • Hybrid Search
    • RAG
    • Document Parsing
    • Dataset Manager
    • Book Manager
    • Citation Engine
    • Multi-modal Knowledge
    • Knowledge Validation
    """

    def __init__(self):

        ##################################################
        # KNOWLEDGE SYSTEMS
        ##################################################

        self.ontology = Ontology()

        self.index = IndexManager()

        self.embeddings = EmbeddingIndex()

        self.retriever = KnowledgeRetriever(

            self.index,

            self.embeddings,

        )

    ##################################################
    # ONTOLOGY
    ##################################################

    def add_concept(

        self,

        concept: str,

    ):

        self.ontology.add_concept(

            concept,

        )

    ##################################################

    def relate(

        self,

        source: str,

        target: str,

    ):

        self.ontology.relate(

            source,

            target,

        )

    ##################################################

    def relationships(

        self,

        concept: str,

    ):

        return self.ontology.relationships(

            concept,

        )

    ##################################################

    def concepts(self):

        return self.ontology.concepts()

    ##################################################
    # DOCUMENT INDEXING
    ##################################################

    def index_document(

        self,

        document_id: str,

        text: str,

    ):

        self.index.index_document(

            document_id,

            text,

        )

    ##################################################

    def remove_document(

        self,

        document_id: str,

    ):

        self.index.remove_document(

            document_id,

        )

    ##################################################

    def keyword_search(

        self,

        query: str,

    ):

        return self.retriever.keyword_search(

            query,

        )

    ##################################################
    # EMBEDDINGS
    ##################################################

    def add_embedding(

        self,

        document_id: str,

        embedding: list[float],

        metadata=None,

    ):

        self.embeddings.add(

            document_id,

            embedding,

            metadata,

        )

    ##################################################

    def get_embedding(

        self,

        document_id: str,

    ):

        return self.embeddings.get(

            document_id,

        )

    ##################################################

    def remove_embedding(

        self,

        document_id: str,

    ):

        self.embeddings.remove(

            document_id,

        )

    ##################################################
    # RETRIEVAL
    ##################################################

    def semantic_search(

        self,

        embedding,

        top_k=5,

    ):

        return self.retriever.semantic_search(

            embedding,

            top_k,

        )

    ##################################################

    def retrieve(

        self,

        query: str,

    ):

        return self.retriever.retrieve(

            query,

        )

    ##################################################
    # INGESTION PIPELINE (Phase F)
    ##################################################

    def ingest_document(
        self,
        document_id: str,
        text: str,
        source: str = "local",
        origin: str = "ingestion",
        version: str = "1",
        metadata=None,
        embed_fn=None,
        embed_batch_fn=None,
        embed_model_id: str = "hercule-hash-test-v1",
        vector_store=None,
        chunk_size: int = 200,
        overlap: int = 40,
    ):
        """INPUT -> TYPE -> PARSE -> NORMALIZE -> CHUNK -> METADATA
        -> EMBEDDING -> INDEX -> PROVENANCE into the owned stores."""
        pipeline = KnowledgeIngestionPipeline(
            index=self.index,
            embeddings=self.embeddings,
            ontology=self.ontology,
            embed_fn=embed_fn,
            embed_batch_fn=embed_batch_fn,
            embed_model_id=embed_model_id,
            vector_store=vector_store,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        return pipeline.ingest(
            document_id,
            text,
            source=source,
            origin=origin,
            version=version,
            metadata=metadata,
        )

    ##################################################

    def hybrid_retrieve(
        self,
        query: str,
        top_k: int = 5,
        strategy=None,
        filters=None,
        vector_store=None,
        embed_fn=None,
    ):
        """Strategy-aware retrieval (keyword/vector/metadata/hybrid).

        Returns a list of plain dicts; ``strategy`` accepts a
        ``RetrievalStrategy`` or its string value.
        """
        if isinstance(strategy, str):
            strategy = RetrievalStrategy(strategy)
        retriever = HybridRetriever(
            index=self.index,
            embeddings=self.embeddings,
            vector_store=vector_store,
            embed_fn=embed_fn,
        )
        return [item.as_dict() for item in retriever.retrieve(query, top_k=top_k, strategy=strategy, filters=filters)]

    ##################################################
    # INDEX DESCRIPTOR & COMPATIBILITY (Phase H)
    ##################################################

    def index_descriptor(self):
        """Infer the unanimous embedding provenance of this index.

        Returns {"provider","model_id","dimension","normalized","version",
        "chunks"}. Raises EMBEDDING_INDEX_INCOMPATIBLE when records mix
        models or dimensions.
        """
        models: dict[str, int] = {}
        dims: dict[int, int] = {}
        for record in self.embeddings.all().values():
            meta = (record or {}).get("metadata") or {}
            prov = meta.get("provenance") or {}
            model = str(meta.get("embedding_model") or prov.get("metadata", {}).get("embedding_model") or "unknown")
            vector = (record or {}).get("embedding") or []
            models[model] = models.get(model, 0) + 1
            dims[len(vector)] = dims.get(len(vector), 0) + 1
        if not models:
            return {"provider": "", "model_id": "", "dimension": self.embeddings.expected_dim or 0,
                    "normalized": None, "version": "", "chunks": 0}
        if len(models) > 1 or len(dims) > 1:
            raise ValueError(
                f"EMBEDDING_INDEX_INCOMPATIBLE: mixed models {sorted(models)} / dims {sorted(dims)}"
            )
        model_id = next(iter(models))
        provider = "hash" if "hash" in model_id else ("sentence-transformers" if "sentence" in model_id else "")
        return {"provider": provider, "model_id": model_id, "dimension": next(iter(dims)),
                "normalized": None, "version": "", "chunks": sum(models.values())}

    ##################################################

    def write_index_metadata(self, metadata=None):
        """Persist the active embedding identity into the index store."""
        descriptor = dict(metadata or self.index_descriptor())
        return self.embeddings.set_index_metadata(descriptor)

    ##################################################

    def check_index_compatibility(self, provider=None, model_id=None, dimension=None, normalized=None):
        """Reject indexes incompatible with the active embedding backend.

        Compares stored metadata (when present) against the given
        provider identity. Raises EMBEDDING_INDEX_INCOMPATIBLE on
        model/dimension/normalization mismatch — never mixes silently.
        Returns the stored descriptor on success.
        """
        stored = self.embeddings.get_index_metadata()
        if provider is not None:
            model_id = model_id or getattr(provider, "model_id", "")
            dimension = dimension or getattr(provider, "dimension", 0) or dimension
            if normalized is None and hasattr(provider, "normalized"):
                normalized = provider.normalized
        problems = []
        if stored.get("model_id") and model_id and stored["model_id"] != model_id:
            problems.append(f"model {stored['model_id']!r} != {model_id!r}")
        if stored.get("dimension") and dimension and int(stored["dimension"]) != int(dimension):
            problems.append(f"dim {stored['dimension']} != {dimension}")
        if stored.get("normalized") is not None and normalized is not None:
            if bool(stored["normalized"]) != bool(normalized):
                problems.append(f"normalized {stored['normalized']} != {normalized}")
        if self.embeddings.expected_dim and dimension and int(self.embeddings.expected_dim) != int(dimension):
            problems.append(f"pinned dim {self.embeddings.expected_dim} != {dimension}")
        if problems:
            raise ValueError("EMBEDDING_INDEX_INCOMPATIBLE: " + "; ".join(problems))
        return dict(stored)

    ##################################################
    # HEALTH
    ##################################################

    def health(self):

        return {

            "concepts": len(

                self.ontology.concepts()

            ),

            "indexed_words": len(

                self.index.vocabulary()

            ),

            "embeddings": self.embeddings.size(),

        }

    ##################################################
    # RESET
    ##################################################

    def reset(self):

        self.ontology.clear()

        self.index.clear()

        self.embeddings.clear()

    ##################################################
    # FUTURE PLACEHOLDERS
    ##################################################

    def build_knowledge_graph(self):
        """
        Build an interconnected
        knowledge graph.
        """
        pass

    ##################################################

    def import_book(self):
        """
        Import books into
        the knowledge base.
        """
        pass

    ##################################################

    def import_dataset(self):
        """
        Import datasets.
        """
        pass

    ##################################################

    def parse_document(self):
        """
        Parse PDF, DOCX,
        TXT, Markdown, etc.
        """
        pass

    ##################################################

    def summarize(self):
        """
        Summarize stored
        knowledge.
        """
        pass

    ##################################################

    def validate(self):
        """
        Validate knowledge
        consistency.
        """
        pass

    ##################################################

    def export(self):
        """
        Export the complete
        knowledge base.
        """
        pass

    ##################################################

    def backup(self):
        """
        Backup all
        knowledge.
        """
        pass

    ##################################################

    def restore(self):
        """
        Restore knowledge
        from backup.
        """
        pass