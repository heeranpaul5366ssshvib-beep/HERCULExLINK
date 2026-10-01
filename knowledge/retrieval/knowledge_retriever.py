from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Knowledge Retriever
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from knowledge.indexing.index_manager import IndexManager
from knowledge.embeddings.embedding_index import EmbeddingIndex


class KnowledgeRetriever:
    """
    Retrieves information from the
    Knowledge System.
    """

    def __init__(

        self,

        index: IndexManager,

        embeddings: EmbeddingIndex,

    ):

        self.index = index

        self.embeddings = embeddings

    ##################################################

    def keyword_search(

        self,

        query: str,

    ):

        return self.index.search(query)

    ##################################################

    def semantic_search(

        self,

        embedding: list[float],

        top_k: int = 5,

    ):

        """
        Placeholder.

        Future:
        - Cosine Similarity
        - FAISS
        - ChromaDB
        """

        documents = []

        for document_id in self.embeddings.all():

            documents.append(document_id)

        return documents[:top_k]

    ##################################################

    def retrieve(

        self,

        query: str,

    ):

        return {

            "keyword": self.keyword_search(query),

            "semantic": [],

        }