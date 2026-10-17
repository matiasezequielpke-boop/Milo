"""Scribe's rag_query tool — Fase 2, retrieval half.

Embeddings go through LiteLLM too (same gateway dependency as chat
completions) so this doesn't need its own provider SDK — just a key.
Reuses OPENAI_API_KEY since `text-embedding-3-small` is the default
model below; point EMBEDDING_MODEL at a different LiteLLM-supported
model and its matching key field if that default ever changes.

The retrieval half (`retrieve_chunks`) needs no API key at all — it's
a plain pgvector cosine-distance query — so it's real and testable
today. What's gated is only the embedding step, both for a document
at ingest time and for the user's query at search time.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Document, DocumentChunk
from app.tools.errors import ToolNotConfiguredError

EMBEDDING_MODEL = "text-embedding-3-small"


def _require_key() -> str:
    key = get_settings().openai_api_key
    if not key:
        raise ToolNotConfiguredError(
            "No OPENAI_API_KEY configured — Scribe's rag_query tool can't embed "
            "text until Fase 2 budget lands. See README."
        )
    return key


async def embed_text(text: str) -> list[float]:
    api_key = _require_key()
    try:
        import litellm  # large; not part of the Vercel deployment (requirements-extras.txt)
    except ImportError as exc:
        raise ToolNotConfiguredError("LiteLLM isn't installed on this server (requirements-extras.txt).") from exc
    response = await litellm.aembedding(model=EMBEDDING_MODEL, input=[text], api_key=api_key)
    return response.data[0]["embedding"]


@dataclass
class RetrievedChunk:
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    distance: float


async def retrieve_chunks(
    db: AsyncSession, *, user_id: uuid.UUID, query_embedding: list[float], limit: int = 5
) -> list[RetrievedChunk]:
    """Nearest-neighbor search over the caller's own documents only.

    No API key required — this only needs a query vector, which the
    caller gets from `embed_text()` (gated) or, in tests, supplies directly.
    """
    distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
    result = await db.execute(
        select(DocumentChunk, Document, distance)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.user_id == user_id, DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return [
        RetrievedChunk(
            document_id=doc.id,
            document_title=doc.title,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            distance=float(dist),
        )
        for chunk, doc, dist in result.all()
    ]
