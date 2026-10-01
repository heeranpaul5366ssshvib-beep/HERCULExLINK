from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Index Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from collections import defaultdict


class IndexManager:
    """
    Keyword index for documents.
    """

    def __init__(self):

        self._index = defaultdict(set)

    ##################################################

    def index_document(
        self,
        document_id: str,
        text: str,
    ):

        words = text.lower().split()

        for word in words:

            self._index[word].add(
                document_id
            )

    ##################################################

    def search(
        self,
        word: str,
    ):

        return list(
            self._index.get(
                word.lower(),
                set(),
            )
        )

    ##################################################

    def remove_document(
        self,
        document_id: str,
    ):

        for docs in self._index.values():

            docs.discard(
                document_id
            )

    ##################################################

    def vocabulary(self):

        return list(self._index.keys())

    ##################################################

    def clear(self):

        self._index.clear()