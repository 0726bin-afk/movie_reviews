"""
cache_check 노드 — RAG 그래프의 첫 노드. 캐시 히트면 바로 END로.

흐름:
  1. exact 매칭 시도 — 질문 문자열 그대로 일치하면 즉시 반환
  2. exact 미스 시 → 질문 임베딩 → similar 매칭 (코사인 유사도 >= threshold)
  3. 둘 다 미스 → cache_hit=False, 다음 노드(route_query)로

Phase 5 변경: async — repo.lookup_*, embedder.aembed_query 모두 await.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from config.settings import settings
from db.repositories.cache_repo import get_cache_repo
from providers.embedding import get_embedding

if TYPE_CHECKING:
    from rag.state import QueryState


async def cache_check(state: "QueryState") -> "QueryState":
    """캐시 조회. 히트하면 answer/sources 채우고 cache_hit=True."""
    t0 = time.perf_counter()
    print("\n▶ [cache_check] 시작")

    question = state.get("question", "")
    repo = get_cache_repo()

    # ---- 레이어 1: exact ----
    hit = await repo.lookup_exact(question)
    if hit is not None:
        latency = (time.perf_counter() - t0) * 1000
        print(f"✓ [cache_check] 완료 — {latency:.0f}ms  (캐시 히트: exact → END)")
        return {
            **state,
            "cache_hit": True,
            "cache_source": "exact",
            "cache_score": 1.0,
            "answer": hit.answer,
            "sources": hit.sources,
            "latency_ms": {**(state.get("latency_ms") or {}), "cache_check": latency},
        }

    # ---- 레이어 2: similar ----
    qe: list[float] | None = None
    try:
        embedder = get_embedding()
        qe = await embedder.aembed_query(question)
        result = await repo.lookup_similar(
            qe, threshold=settings.CACHE_SIMILARITY_THRESHOLD
        )
    except Exception:
        result = None

    if result is not None:
        entry, score = result
        latency = (time.perf_counter() - t0) * 1000
        print(f"✓ [cache_check] 완료 — {latency:.0f}ms  (캐시 히트: similar, score={score:.3f} → END)")
        return {
            **state,
            "cache_hit": True,
            "cache_source": "similar",
            "cache_score": score,
            "answer": entry.answer,
            "sources": entry.sources,
            "_question_embedding": qe,
            "latency_ms": {**(state.get("latency_ms") or {}), "cache_check": latency},
        }

    # ---- 미스 ----
    latency = (time.perf_counter() - t0) * 1000
    print(f"✓ [cache_check] 완료 — {latency:.0f}ms  (캐시 미스 → route_query로)")
    out: dict = {
        **state,
        "cache_hit": False,
        "latency_ms": {**(state.get("latency_ms") or {}), "cache_check": latency},
    }
    if qe is not None:
        out["_question_embedding"] = qe
    return out
