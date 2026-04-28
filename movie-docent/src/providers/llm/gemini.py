"""
Gemini LLM 어댑터.

LangChain의 `ChatGoogleGenerativeAI`를 우리 `LLMProvider` ABC에 맞춰 래핑.
노드/체인 코드는 이 클래스의 존재를 모르고, 팩토리(`get_llm()`)에서 받음.

설계 메모:
- `invoke`/`ainvoke`/`stream`/`astream` 4개 메소드만 노출
- 입력은 str 또는 [{role, content}, ...] (PromptInput) — LangChain Message 형식 강제 안 함
- API 키 없으면 생성은 되지만 실제 호출 시점에 에러
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import settings
from providers.base import LLMProvider, PromptInput


class GeminiLLM(LLMProvider):
    """`ChatGoogleGenerativeAI` 위에 LLMProvider 인터페이스를 씌운 얇은 래퍼."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self._model_name = model
        self._client = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
            max_output_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            google_api_key=settings.GEMINI_API_KEY or None,
        )

    # ---- 내부 변환기 ----------------------------------------------

    @staticmethod
    def _to_messages(prompt: PromptInput) -> list:
        """str 또는 [{role, content}, ...] → LangChain BaseMessage 리스트."""
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
        """LangChain 응답에서 텍스트만 뽑기."""
        text = getattr(result, "content", None)
        if text is None:
            return str(result)
        # content가 list of content blocks인 경우 (최신 버전 대응)
        if isinstance(text, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in text
            )
        return str(text)

    # ---- LLMProvider 구현 ------------------------------------------

    def invoke(self, prompt: PromptInput) -> str:
        result = self._client.invoke(self._to_messages(prompt))
        return self._extract_text(result)

    async def ainvoke(self, prompt: PromptInput) -> str:
        result = await self._client.ainvoke(self._to_messages(prompt))
        return self._extract_text(result)

    def stream(self, prompt: PromptInput) -> Iterator[str]:
        for chunk in self._client.stream(self._to_messages(prompt)):
            text = self._extract_text(chunk)
            if text:
                yield text

    def astream(self, prompt: PromptInput) -> AsyncIterator[str]:
        # `def astream` 시그니처를 유지하면서 async generator를 반환.
        # 내부 `_gen()`이 async generator라 호출 시 AsyncIterator를 돌려준다.
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
