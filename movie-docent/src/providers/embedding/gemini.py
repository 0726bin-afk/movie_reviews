"""
Gemini Embedding 어댑터.

LangChain GoogleGenerativeAIEmbeddings를 EmbeddingProvider ABC에 맞춰 래핑.

설계:
- 모델명은 settings.EMBEDDING_MODEL_NAME에서 가져옴 (.env 또는 default)
- 차원은 settings.EMBEDDING_DIMENSION — schema의 vector(N)과 반드시 일치
- gemini-embedding-001 기본 3072 → output_dimensionality 인자로 768 강제
- LangChain 버전이 output_dimensionality를 지원 안 하면 fallback (모델 native dim 사용)

차원 mismatch 발생 시 schema의 vector(N) 또는 settings.EMBEDDING_DIMENSION 둘 중 하나 맞춰야 함.

사용 가능 모델 진단:
    python -c "
    import google.generativeai as genai
    import os
    genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    for m in genai.list_models():
        if 'embedContent' in m.supported_generation_methods:
            print(m.name)
    "
"""
from __future__ import annotations

from collections.abc import Sequence

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config.settings import settings
from providers.base import EmbeddingProvider


def _build_client(model: str, dimension: int) -> GoogleGenerativeAIEmbeddings:
    """
    GoogleGenerativeAIEmbeddings 생성.
    output_dimensionality 인자 지원 여부가 라이브러리 버전마다 달라
    TypeError 시 fallback.
    """
    common_kwargs = {
        "model": model,
        "google_api_key": settings.GEMINI_API_KEY or None,
    }
    try:
        return GoogleGenerativeAIEmbeddings(
            **common_kwargs,
            output_dimensionality=dimension,
        )
    except TypeError:
        # 구 버전 langchain-google-genai — output_dimensionality 미지원.
        # gemini-embedding-001은 default 3072가 됨 → schema mismatch 위험.
        # 이때는 EMBEDDING_DIMENSION을 모델 native dim과 맞추거나
        # langchain-google-genai 업그레이드 필요.
        return GoogleGenerativeAIEmbeddings(**common_kwargs)


class GeminiEmbedding(EmbeddingProvider):
    """GoogleGenerativeAIEmbeddings를 EmbeddingProvider 인터페이스로 래핑."""

    def __init__(
        self,
        model: str | None = None,
        dimension: int | None = None,
    ):
        self._model_name = model or settings.EMBEDDING_MODEL_NAME
        self._dimension = dimension or settings.EMBEDDING_DIMENSION
        self._client = _build_client(self._model_name, self._dimension)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._client.embed_documents(list(texts))

    async def aembed_query(self, text: str) -> list[float]:
        return await self._client.aembed_query(text)

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._client.aembed_documents(list(texts))

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name
