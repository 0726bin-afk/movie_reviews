"""
Claude(Anthropic) LLM 어댑터 — A/B 비교용 (Phase 4 stretch).

Gemini 패턴 그대로 재사용. langchain-anthropic 의존성은 pyproject에서 주석 처리.

사용:
    .env에서 LLM_PROVIDER=claude로 전환
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config.settings import settings
from providers.base import LLMProvider, PromptInput


class ClaudeLLM(LLMProvider):
    """`ChatAnthropic` 위에 LLMProvider 인터페이스를 씌운 얇은 래퍼."""

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-latest",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise ImportError(
                "Claude 사용하려면 pyproject의 'langchain-anthropic' 주석 해제 후 "
                "`pip install -e .`로 재설치 필요."
            ) from e

        self._model_name = model
        self._client = ChatAnthropic(
            model=model,
            temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            api_key=settings.ANTHROPIC_API_KEY or None,
        )

    @staticmethod
    def _to_messages(prompt: PromptInput) -> list:
        if isinstance(prompt, str):
            return [HumanMessage(content=prompt)]
        msgs: list = []
        for m in prompt:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                msgs.append(SystemMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
            else:
                msgs.append(HumanMessage(content=content))
        return msgs

    @staticmethod
    def _extract_text(result) -> str:
        text = getattr(result, "content", None)
        if text is None:
            return str(result)
        if isinstance(text, list):
            return "".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in text
            )
        return str(text)

    def invoke(self, prompt: PromptInput) -> str:
        return self._extract_text(self._client.invoke(self._to_messages(prompt)))

    async def ainvoke(self, prompt: PromptInput) -> str:
        return self._extract_text(await self._client.ainvoke(self._to_messages(prompt)))

    def stream(self, prompt: PromptInput) -> Iterator[str]:
        for chunk in self._client.stream(self._to_messages(prompt)):
            text = self._extract_text(chunk)
            if text:
                yield text

    def astream(self, prompt: PromptInput) -> AsyncIterator[str]:
        client = self._client
        to_messages = self._to_messages
        extract_text = self._extract_text

        async def _gen() -> AsyncIterator[str]:
            async for chunk in client.astream(to_messages(prompt)):
                text = extract_text(chunk)
                if text:
                    yield text

        return _gen()

    @property
    def model_name(self) -> str:
        return self._model_name
