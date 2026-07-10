"""bge-m3 embedding model wrapper (detailed_plan.md 4.2).

Loaded lazily and cached: instantiating `HuggingFaceEmbeddings` downloads/loads the
model weights, which is slow and unnecessary for requests that never touch RAG.
"""

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import get_settings


@lru_cache
def get_embedder() -> HuggingFaceEmbeddings:
    settings = get_settings()
    return HuggingFaceEmbeddings(model_name=settings.embedding_model_name)
