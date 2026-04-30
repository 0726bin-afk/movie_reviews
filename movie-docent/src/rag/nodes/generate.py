"""
generate 노드 — query_type에 맞는 프롬프트로 LLM에 답변 생성을 위임.

state -> state.
입력: question, retrieved_docs, grounding_docs, query_type
출력: answer, sources

Phase 5 변경: async — llm.ainvoke 사용.
프롬프트 선택은 rag.prompts.get_prompt_for(query_type)이 책임.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from providers.llm import get_llm
from rag.parsers.answer_parser import split_answer_and_sources
from rag.prompts import get_prompt_for

if TYPE_CHECKING:
    from core.types import RetrievedDoc
    from rag.state import QueryState


def _format_docs(docs: "list[RetrievedDoc]") -> str:
    """RetrievedDoc 리스트 → {context} 자리 텍스트."""
    if not docs:
        return "(검색 결과 없음)"
    lines = []
    for i, d in enumerate(docs, 1):
        title = d.metadata.get("title") if d.metadata else None
        meta = f" [{title}]" if title else ""
        lines.append(f"{i}. ({d.source}#{d.source_id}){meta} {d.text}")
    return "\n".join(lines)


async def generate(state: "QueryState") -> "QueryState":
    """LLM 호출해서 답변 생성. async — llm.ainvoke."""
    t0 = time.perf_counter()
    print("\n▶ [generate] 시작  (LLM 호출 중...)")

    question = state.get("question", "")
    docs = (state.get("retrieved_docs") or []) + (state.get("grounding_docs") or [])
    query_type = state.get("query_type") or "basic_info"

    prompt = get_prompt_for(query_type)
    llm = get_llm()

    prompt_value = prompt.format_prompt(
        question=question,
        context=_format_docs(docs),
    )
    raw_answer = await llm.ainvoke(prompt_value.to_string())

    body, sources = split_answer_and_sources(raw_answer, docs=docs)

    latency = (time.perf_counter() - t0) * 1000
    print(f"✓ [generate] 완료 — {latency:.0f}ms  (출처 {len(sources)}건 포함)")
    return {
        **state,
        "answer": body,
        "sources": sources,
        "latency_ms": {**(state.get("latency_ms") or {}), "generate": latency},
    }
