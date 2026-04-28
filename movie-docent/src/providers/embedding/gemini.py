"""
Gemini Embedding 어댑터.

LangChain의 `GoogleGenerativeAIEmbeddings`를 우리 `EmbeddingProvider` ABC에 맞춰 래핑.

설계 메모:
- 모델 기본값은 `models/text-embedding-004` — 768차원 (settings.EMBEDDING_DIMENSION과 일치)
- DB schema의 vector(N) 차원과 반드시 일치해야 함. 모델 교체 시 `scripts/reembed.py`로 무중단 스왑.
"""
from __future__ import annotations

from collections.abc import Sequence

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config.settings import settings
from providers.base import EmbeddingProvider


class GeminiEmbedding(EmbeddingProvider):
    """`GoogleGenerativeAIEmbeddings`를 EmbeddingProvider 인터페이스로 래핑."""

    def __init__(
        self,
        model: str = "models/text-embedding-004",
        dimension: int | None = None,
    ):
        self._model_name = model
        self._dimension = dimension or settings.EMBEDDING_DIMENSION
        self._client = GoogleGenerativeAIEmbeddings(
            model=model,
            google_api_key=settings.GEMINI_API_KEY or None,
        )

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._client.embed_documents(list(texts))

    async def aembed_query(self, text: str) -> list[float]:
        # GoogleGenerativeAIEmbeddings에 aembed_query가 있음
        return await self._client.aembed_query(text)

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._client.aembed_documents(list(texts))

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name
