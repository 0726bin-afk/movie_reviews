"""
모델 프로바이더 추상화.

설계 원칙:
- 노드/체인 코드는 LangChain SDK를 직접 import하지 않음
- 대신 이 모듈의 ABC만 알고, 팩토리(`get_llm()` 등)에서 구현체를 받음
- 새 모델 추가 = ABC 구현체 1개 + 팩토리 분기 한 줄 추가

세 종류의 추상화:
- LLMProvider: 답 생성용 (Gemini / GPT / Claude / Fake)
- EmbeddingProvider: 텍스트 → 벡터 (Gemini / OpenAI 등)
- TaggerProvider: 리뷰 해시태그 추출 (Gemma 등 OSS)

이 모듈은 어떤 외부 SDK도 import하지 않는다. 구현체에서만 사용.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator, Sequence


PromptInput = str | list[dict]


class LLMProvider(ABC):
    """LLM 추상화. 답 생성용."""

    @abstractmethod
    def invoke(self, prompt: PromptInput) -> str:
        """동기 호출. 답 전체를 한 번에 반환."""
        ...

    @abstractmethod
    async def ainvoke(self, prompt: PromptInput) -> str:
        """비동기 호출."""
        ...

    @abstractmethod
    def stream(self, prompt: PromptInput) -> Iterator[str]:
        """동기 스트리밍."""
        ...

    @abstractmethod
    def astream(self, prompt: PromptInput) -> AsyncIterator[str]:
        """비동기 스트리밍."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """현재 모델 식별자 (로깅용)."""
        ...


class EmbeddingProvider(ABC):
    """텍스트 → 벡터 변환 추상화."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """단일 쿼리 임베딩."""
        ...

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """여러 문서 일괄 임베딩."""
        ...

    @abstractmethod
    async def aembed_query(self, text: str) -> list[float]:
        """단일 쿼리 비동기 임베딩."""
        ...

    @abstractmethod
    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """여러 문서 비동기 일괄 임베딩."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """임베딩 차원수. DB 스키마와 일치 필수."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...


class TaggerProvider(ABC):
    """리뷰 해시태그 추출 추상화 (Gemma 등 OSS)."""

    @abstractmethod
    def tag(self, review_text: str, movie_context: dict | None = None) -> list[str]:
        """리뷰 1건의 해시태그 리스트 반환."""
        ...

    def tag_batch(
        self,
        review_texts: Sequence[str],
        movie_context: dict | None = None,
    ) -> list[list[str]]:
        """배치 처리. 기본 구현은 순차 호출."""
        return [self.tag(t, movie_context) for t in review_texts]

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str:
        """tagger_version DB 필드용. 모델·프롬프트 변경 시 변경."""
        ...
