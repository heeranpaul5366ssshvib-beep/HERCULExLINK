from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Runtime Cache
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


class CacheEntry:

    def __init__(
        self,
        value: Any,
        ttl: int,
    ):

        self.value = value

        self.created = datetime.now(timezone.utc)

        self.expires = self.created + timedelta(
            seconds=ttl
        )

    @property
    def expired(self) -> bool:

        return datetime.now(timezone.utc) >= self.expires


class RuntimeCache:
    """
    Runtime cache for expensive
    intelligence computations.
    """

    def __init__(self):

        self.initialized = False

        self.cache: Dict[str, CacheEntry] = {}

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Runtime Cache"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        self.cache.clear()

        self.initialized = False

    # --------------------------------------------------

    def put(
        self,
        key: str,
        value: Any,
        ttl: int = 300,
    ):

        self.cache[key] = CacheEntry(
            value,
            ttl,
        )

    # --------------------------------------------------

    def get(
        self,
        key: str,
    ) -> Optional[Any]:

        entry = self.cache.get(key)

        if entry is None:

            return None

        if entry.expired:

            self.cache.pop(key, None)

            return None

        return entry.value

    # --------------------------------------------------

    def contains(
        self,
        key: str,
    ) -> bool:

        return self.get(key) is not None

    # --------------------------------------------------

    def remove(
        self,
        key: str,
    ):

        self.cache.pop(key, None)

    # --------------------------------------------------

    def clear(self):

        self.cache.clear()

    # --------------------------------------------------

    def cleanup(self):

        expired = [

            key

            for key, value in self.cache.items()

            if value.expired

        ]

        for key in expired:

            self.cache.pop(key, None)

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

            "entries": len(self.cache),

        }