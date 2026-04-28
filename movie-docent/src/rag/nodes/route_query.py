"""
route_query 노드 — 질문을 5종 query_type 중 하나로 분류.

state -> state.
입력: question
출력: query_type, target_movie

설계:
- LLM 출력에서 카테고리 단어를 substring으로 매칭
- 미매칭 시 'basic_info' fallback
- target_movie는 따옴표/꺾쇠 휴리스틱
- Phase 5: async — llm.ainvoke 사용
"""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from providers.llm import get_llm
from rag.prompts.router import router_prompt

if TYPE_CHECKING:
    from rag.state import QueryState


VALID_QUERY_TYPES = (
    "basic_info",
    "review_summary",
    "tmi",
    "polarity",
    "recommendation",
)


def _extract_target_movie(question: str) -> str | None:
    """따옴표·꺾쇠 안 텍스트가 있으면 영화 제목으로 간주."""
    for pat in [r'"([^"]+)"', r'「([^」]+)」', r'《([^》]+)》', r'<([^>]+)>']:
        m = re.search(pat, question)
        if m:
            return m.group(1).strip()
    return None


def _parse_query_type(raw: str) -> str:
    """LLM 출력에서 카테고리명 substring matching."""
    text = raw.strip().lower()
    for cat in VALID_QUERY_TYPES:
        if cat in text:
            return cat
    return "basic_info"


async def route_query(state: "QueryState") -> "QueryState":
    """질문 → query_type. async — llm.ainvoke."""
    t0 = time.perf_counter()

    question = state.get("question", "")
    llm = get_llm()

    prompt_value = router_prompt.format_prompt(question=question)
    raw = await llm.ainvoke(prompt_value.to_string())
    query_type = _parse_query_type(raw)

    target_movie = state.get("target_movie") or _extract_target_movie(question)

    latency = (time.perf_counter() - t0) * 1000
    return {
        **state,
        "query_type": query_type,
        "target_movie": target_movie,
        "latency_ms": {**(state.get("latency_ms") or {}), "route_query": latency},
    }
