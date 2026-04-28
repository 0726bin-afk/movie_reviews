"""
cache_check 노드 — RAG 그래프의 첫 노드. 캐시 히트면 바로 END로.

흐름:
  1. exact 매칭 시도 — 질문 문자열 그대로 일치하면 즉시 반환
  2. exact 미스 시 → 질문 임베딩 → similar 매칭 (코사인 유사도 ≥ threshold)
  3. 둘 다 미스 → cache_hit=False, 다음 노드(route_query)로

state -> state 시그니처.
입력: question
출력: cache_hit, cache_source, cache_score, answer, sources (히트 시)
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from config.settings import settings
from db.repositories.cache_repo import get_cache_repo
from providers.embedding import get_embedding

if TYPE_CHECKING:
    from rag.state import QueryState


def cache_check(state: "QueryState") -> "QueryState":
    """캐시 조회. 히트하면 answer/sources 채우고 cache_hit=True."""
    t0 = time.perf_counter()

    question = state.get("question", "")
    repo = get_cache_repo()

    # ---- 레이어 1: exact ----
    hit = repo.lookup_exact(question)
    if hit is not None:
        latency = (time.perf_counter() - t0) * 1000
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
    try:
        embedder = get_embedding()
        qe = embedder.embed_query(question)
        result = repo.lookup_similar(qe, threshold=settings.CACHE_SIMILARITY_THRESHOLD)
    except Exception:
        # 임베딩 호출 실패(API 키 없음 등)도 캐시 미스로 처리. 다음 노드가 돌아감.
        result = None

    if result is not None:
        entry, score = result
        latency = (time.perf_counter() - t0) * 1000
        return {
            **state,
            "cache_hit": True,
            "cache_source": "similar",
            "cache_score": score,
            "answer": entry.answer,
            "sources": entry.sources,
            # 다음 cache 저장 시 임베딩 재사용 가능하도록 state에 임시 보관
            "_question_embedding": qe,
            "latency_ms": {**(state.get("latency_ms") or {}), "cache_check": latency},
        }

    # ---- 미스 ----
    latency = (time.perf_counter() - t0) * 1000
    out: dict = {
        **state,
        "cache_hit": False,
        "latency_ms": {**(state.get("latency_ms") or {}), "cache_check": latency},
    }
    # 임베딩이 미스 시점에 이미 만들어졌다면 save_cache가 재사용
    try:
        out["_question_embedding"] = qe  # type: ignore[name-defined]
    except NameError:
        pass
    return out
