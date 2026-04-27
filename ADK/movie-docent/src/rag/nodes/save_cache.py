"""
save_cache 노드 — generate 직후 답변을 캐시에 저장.

cache_hit이면 이 노드는 진입하지 않음 (조건부 분기로 우회).
generate 결과가 비어 있으면 저장 스킵 (사고로 빈 답이 캐시에 들어가는 것 방지).

state -> state 시그니처.
입력: question, answer, sources, _question_embedding (cache_check가 만들어둠)
출력: 변경 없음 — side effect만 (CacheRepo.save 호출)
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from db.repositories.cache_repo import CachedEntry, get_cache_repo
from providers.embedding import get_embedding

if TYPE_CHECKING:
    from rag.state import QueryState


def save_cache(state: "QueryState") -> "QueryState":
    """답변을 캐시에 저장. 답변이 비어 있으면 스킵."""
    t0 = time.perf_counter()

    answer = (state.get("answer") or "").strip()
    if not answer:
        return state  # 빈 답 저장 안 함

    question = state.get("question", "")
    sources = state.get("sources") or []

    # cache_check 단계에서 임베딩이 만들어졌으면 재사용. 아니면 새로 계산 (예: 그래프 진입점이 cache_check가 아닐 때).
    qe = state.get("_question_embedding")  # type: ignore[call-overload]
    if qe is None:
        try:
            qe = get_embedding().embed_query(question)
        except Exception:
            qe = None  # 임베딩 실패해도 exact 매칭용으로는 저장

    entry = CachedEntry(
        question=question,
        answer=answer,
        sources=list(sources),
        embedding=qe,
    )
    try:
        get_cache_repo().save(entry)
    except Exception:
        # 캐시 저장 실패는 답변 반환을 막지 않음 — 로깅만 (Phase 5 logger 추가)
        pass

    latency = (time.perf_counter() - t0) * 1000
    return {
        **state,
        "latency_ms": {**(state.get("latency_ms") or {}), "save_cache": latency},
    }
