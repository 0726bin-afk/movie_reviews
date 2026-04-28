"""
generate 노드 — query_type에 맞는 프롬프트로 LLM에 답변 생성을 위임.

state -> state 시그니처.
입력: question, retrieved_docs, grounding_docs, query_type
출력: answer (+ latency_ms 갱신)

설계 메모:
- 프롬프트 선택은 `rag.prompts.get_prompt_for(query_type)`이 책임짐
- LLM 호출은 팩토리(`get_llm()`)가 책임짐 — 모델 교체 영향 없음
- retrieved_docs + grounding_docs를 합쳐 {context}로 직렬화
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
    """RetrievedDoc 리스트 → 프롬프트 {context} 자리에 들어갈 텍스트."""
    if not docs:
        return "(검색 결과 없음)"
    lines = []
    for i, d in enumerate(docs, 1):
        title = d.metadata.get("title") if d.metadata else None
        meta = f" [{title}]" if title else ""
        lines.append(f"{i}. ({d.source}#{d.source_id}){meta} {d.text}")
    return "\n".join(lines)


def generate(state: "QueryState") -> "QueryState":
    """LLM 호출해서 답변 생성."""
    t0 = time.perf_counter()

    question = state.get("question", "")
    docs = (state.get("retrieved_docs") or []) + (state.get("grounding_docs") or [])
    query_type = state.get("query_type") or "basic_info"

    prompt = get_prompt_for(query_type)
    llm = get_llm()

    prompt_value = prompt.format_prompt(
        question=question,
        context=_format_docs(docs),
    )
    raw_answer = llm.invoke(prompt_value.to_string())

    # 본문/출처 분리 — state.answer는 본문, state.sources는 Citation 리스트
    body, sources = split_answer_and_sources(raw_answer, docs=docs)

    latency = (time.perf_counter() - t0) * 1000
    return {
        **state,
        "answer": body,
        "sources": sources,
        "latency_ms": {**(state.get("latency_ms") or {}), "generate": latency},
    }
