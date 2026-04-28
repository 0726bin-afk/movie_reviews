"""
LLM 팩토리.

`get_llm()`이 `settings.LLM_PROVIDER`를 읽어 구현체를 라우팅.
이게 모델 교체의 단일 지점 — `.env`에서 LLM_PROVIDER만 바꾸면 됨.

사용 예:
    from providers.llm import get_llm
    llm = get_llm()
    answer = llm.invoke("기생충 줄거리?")

Lazy import로 미사용 provider의 import 비용 안 냄.
새 모델 추가 = ABC 구현체 + 여기 분기 한 줄.
"""
from __future__ import annotations

from config.settings import settings
from providers.base import LLMProvider


def get_llm() -> LLMProvider:
    """settings.LLM_PROVIDER 값으로 구현체를 라우팅."""
    provider = settings.LLM_PROVIDER

    if provider == "gemini":
        from providers.llm.gemini import GeminiLLM
        return GeminiLLM()

    if provider == "fake":
        # Phase 4에서 작성 예정 — 지금은 import 시도 시 에러
        from providers.llm.fake import FakeLLM  # noqa: F401
        return FakeLLM()

    if provider == "openai":
        from providers.llm.openai import OpenAILLM  # noqa: F401
        return OpenAILLM()

    if provider == "claude":
        from providers.llm.claude import ClaudeLLM  # noqa: F401
        return ClaudeLLM()

    raise ValueError(
        f"Unknown LLM_PROVIDER: {provider!r}. "
        f"Choose from gemini, openai, claude, fake."
    )


__all__ = ["get_llm"]
