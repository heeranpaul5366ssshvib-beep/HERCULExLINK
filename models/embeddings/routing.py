from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Embedding Routing Authority
Author: Heeran Paul
License: MIT
--------------------------------------------

Embedding requests flow through the capability router — no manager
bypasses it. ``select_embedding_model`` routes (capability =
EMBEDDING) and validates that the embedding manager actually holds a
provider for the selected model. Anything else fails loudly instead
of silently substituting another backend.
"""

from typing import Any


def select_embedding_model(task: str, router: Any, manager: Any = None) -> str:
    """Return the routed embedding model id for ``task``.

    Raises the router's ``ModelRoutingFailure`` when nothing is
    capable, or ``EmbeddingUnavailableError`` when the manager has no
    provider for the routed model (never silently swapped).
    """
    model_id, _decision = router.route_embedding(task)
    if manager is not None and model_id not in getattr(manager, "providers", {}):
        from models.embeddings.provider import EmbeddingUnavailableError

        raise EmbeddingUnavailableError(
            f"routed embedding model '{model_id}' has no registered provider"
        )
    return model_id


def route_and_embed(
    manager: Any,
    router: Any,
    texts: Any,
    task: str = "",
    batch: bool = False,
    correlation_id: str = "",
) -> Any:
    """Route then embed (single str or batch) through the manager."""
    model_id = select_embedding_model(task, router, manager)
    if batch:
        return manager.embed_batch(list(texts), model=model_id, correlation_id=correlation_id)
    return manager.embed(str(texts), model=model_id, correlation_id=correlation_id)
