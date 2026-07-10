"""Chroma vector-store client (detailed_plan.md 1.2).

Vectors live here, keyed by `chunk_id`; the chunk's text/metadata stay in Postgres
(`document_chunks`, app/models/document_chunk.py). Embeddings are computed by
app/services/embeddings.py and passed in explicitly -- the collection is created
without an embedding function so `add`/`query` always require pre-computed vectors.
"""

from functools import lru_cache

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.config import get_settings


@lru_cache
def get_chroma_client() -> chromadb.ClientAPI:
    settings = get_settings()
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def get_chunk_collection() -> Collection:
    settings = get_settings()
    return get_chroma_client().get_or_create_collection(name=settings.chroma_collection_name)
