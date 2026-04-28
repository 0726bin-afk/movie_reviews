"""
FakeLLM — 결정적 출력 LLM. 테스트 전용.

용도:
- 단위 테스트에서 외부 API 호출 없이 그래프 동작 검증
- API 키 미발급 상태에서 mvp_chain·graph가 import만 되는지 확인
- CI 환경에서 빠르게 토폴로지 회귀 테스트

사용:
    .env에서 LLM_PROVIDER=fake로 변경 → get_llm()이 이 클래스 반환

설계:
- invoke/ainvoke는 고정 문자열 또는 callback의 결과 반환
- stream/astream은 한 번에 전체 응답을 yield (chunked simulation X)
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator

from providers.base import LLMProvider, PromptInput


_DEFAULT_RESPONSE = (
    "(Fake LLM response — 실제 모델이 호출되지 않았습니다. "
    "LLM_PROVIDER를 gemini/openai/claude 중 하나로 변경하세요.)\n\n"
    "출처: fake-llm"
)


class FakeLLM(LLMProvider):
    """결정적 응답 LLM. 토폴로지·인터페이스 검증용."""

    def __init__(
        self,
        response: str | Callable[[PromptInput], str] = _DEFAULT_RESPONSE,
        model_name: str = "fake-llm-v1",
    ):
        self._response = response
        self._model_name = model_name

    def _resolve(self, prompt: PromptInput) -> str:
        if callable(self._response):
            return self._response(prompt)
        return self._response

    def invoke(self, prompt: PromptInput) -> str:
        return self._resolve(prompt)

    async def ainvoke(self, prompt: PromptInput) -> str:
        return self._resolve(prompt)

    def stream(self, prompt: PromptInput) -> Iterator[str]:
        yield self._resolve(prompt)

    def astream(self, prompt: PromptInput) -> AsyncIterator[str]:
        response = self._resolve(prompt)

        async def _gen() -> AsyncIterator[str]:
            yield response

        return _gen()

    @property
    def model_name(self) -> str:
        return self._model_name
