from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Execution Context
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4


class ExecutionContext:
    """
    Shared execution context used
    throughout the Intelligence Runtime.
    """

    def __init__(

        self,

        request: Any,

        source: str = "runtime",

    ):

        self.execution_id = str(uuid4())

        self.created = datetime.now(timezone.utc)

        self.source = source

        self.request = request

        self.data: Dict[str, Any] = {}

        self.metadata: Dict[str, Any] = {}

    # --------------------------------------------------

    def set(

        self,

        key: str,

        value: Any,

    ) -> None:

        self.data[key] = value

    # --------------------------------------------------

    def get(

        self,

        key: str,

        default=None,

    ):

        return self.data.get(

            key,

            default,

        )

    # --------------------------------------------------

    def update(

        self,

        values: Dict[str, Any],

    ):

        self.data.update(values)

    # --------------------------------------------------

    def add_metadata(

        self,

        key: str,

        value: Any,

    ):

        self.metadata[key] = value

    # --------------------------------------------------

    def serialize(self):

        return {

            "execution_id": self.execution_id,

            "created": self.created.isoformat(),

            "source": self.source,

            "request": self.request,

            "data": self.data,

            "metadata": self.metadata,

        }

    # --------------------------------------------------

    def clear(self):

        self.data.clear()

        self.metadata.clear()