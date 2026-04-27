"""
Embedding 팩토리.

`get_embedding()`이 `settings.EMBEDDING_PROVIDER`를 읽어 구현체를 라우팅.

사용 예:
    from providers.embedding import get_embedding
    embedder = get_embedding()
    vec = embedder.embed_query("기생충 줄거리?")
"""
from __future__ import annotations

from config.settings import settings
from providers.base import EmbeddingProvider


def get_embedding() -> EmbeddingProvider:
    """settings.EMBEDDING_PROVIDER 값으로 구현체를 라우팅."""
    provider = settings.EMBEDDING_PROVIDER

    if provider == "gemini":
        from providers.embedding.gemini import GeminiEmbedding
        return GeminiEmbedding()

    if provider == "openai":
        from providers.embedding.openai import OpenAIEmbedding  # noqa: F401
        return OpenAIEmbedding()

    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER: {provider!r}. "
        f"Choose from gemini, openai."
    )


__all__ = ["get_embedding"]
