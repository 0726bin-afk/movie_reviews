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


# ============================================================
# 메시지 타입 (간단 dict 형태로 통일)
# ============================================================
# LangChain BaseMessage에 의존하지 않기 위해 dict 형태로 받음.
# 예: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
# 단순 string도 받음 (자동으로 user 메시지로 처리).
PromptInput = str | list[dict]


# ============================================================
# LLMProvider
# ============================================================

class LLMProvider(ABC):
    """
    LLM 추상화. 답 생성용.

    구현체는 LangChain의 BaseChatModel을 내부에 들고, 메소드 4개를 위임 호출.
    """

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
        """동기 스트리밍. 토큰(또는 청크) 단위 yield."""
        ...

    @abstractmethod
    def astream(self, prompt: PromptInput) -> AsyncIterator[str]:
        """비동기 스트리밍. FastAPI SSE 응답에 사용."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """현재 모델 식별자 (로깅·메트릭용). 예: 'gemini-1.5-pro-002'"""
        ...


# ============================================================
# EmbeddingProvider
# ============================================================

class EmbeddingProvider(ABC):
    """
    텍스트 → 벡터 변환 추상화.

    `dimension`은 DB schema의 vector 컬럼 차원과 반드시 일치해야 함.
    모델 교체로 차원이 달라지면 `scripts/reembed.py`로 무중단 스왑.
    """

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """단일 쿼리 임베딩."""
        ...

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """여러 문서 일괄 임베딩 (배치 효율)."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """임베딩 차원수. DB 스키마와 일치 필수."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...


# ============================================================
# TaggerProvider
# ============================================================

class TaggerProvider(ABC):
    """
    리뷰 해시태그 추출 추상화 (Gemma 등 OSS).

    `version` 속성은 DB의 `reviews.tagger_version`과 매칭됨.
    모델 교체 시 반드시 다른 문자열로 바꿔서 A/B 비교·롤백 가능하게 유지.
    """

    @abstractmethod
    def tag(self, review_text: str, movie_context: dict | None = None) -> list[str]:
        """
        리뷰 1건의 해시태그 리스트 반환.

        Args:
            review_text: 리뷰 원문
            movie_context: {"title": ..., "genres": [...]} 등 보조 정보 (선택)

        Returns:
            ["#연기호평", "#감정몰입", ...] — `tagging/prompts.py` 화이트리스트 내
        """
        ...

    def tag_batch(
        self,
        review_texts: Sequence[str],
        movie_context: dict | None = None,
    ) -> list[list[str]]:
        """
        배치 처리. 기본 구현은 순차 호출.
        구현체가 override해서 진짜 배치 추론으로 최적화 권장.
        """
        return [self.tag(t, movie_context) for t in review_texts]

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str:
        """tagger_version DB 필드용. 모델·프롬프트 변경 시 반드시 변경."""
        ...
