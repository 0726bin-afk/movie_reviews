"""
save_cache 노드 — generate 직후 답변을 캐시에 저장.

cache_hit이면 그래프가 이 노드를 거치지 않고 END로 가게 와이어링됨.
generate 결과가 비어 있으면 저장 스킵.

Phase 5 변경: async — repo.save, embedder.aembed_query 모두 await.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from db.repositories.cache_repo import CachedEntry, get_cache_repo
from providers.embedding import get_embedding

if TYPE_CHECKING:
    from rag.state import QueryState


async def save_cache(state: "QueryState") -> "QueryState":
    """답변을 캐시에 저장. 답변이 비어 있으면 스킵."""
    t0 = time.perf_counter()
    print("\n▶ [save_cache] 시작")

    answer = (state.get("answer") or "").strip()
    if not answer:
        print("✓ [save_cache] 완료 — 0ms  (답변 없음, 저장 스킵)")
        return state

    question = state.get("question", "")
    sources = state.get("sources") or []

    qe = state.get("_question_embedding")
    if qe is None:
        try:
            qe = await get_embedding().aembed_query(question)
        except Exception:
            qe = None

    entry = CachedEntry(
        question=question,
        answer=answer,
        sources=list(sources),
        embedding=qe,
    )
    try:
        await get_cache_repo().save(entry)
    except Exception:
        pass

    latency = (time.perf_counter() - t0) * 1000
    print(f"✓ [save_cache] 완료 — {latency:.0f}ms")
    return {
        **state,
        "latency_ms": {**(state.get("latency_ms") or {}), "save_cache": latency},
    }
