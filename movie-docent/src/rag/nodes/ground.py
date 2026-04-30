"""
ground 노드 — 실시간 그라운딩 (DuckDuckGo).

흐름:
  1. retrieve가 먼저 DB에서 자료 조회
  2. tmi 류 질문 + 자료 부족 → graph가 이 노드로 라우팅
  3. 질문에서 관심 카테고리 추출 (키워드 매칭) — 기본은 비하인드
  4. target_movie가 DB에 있으면 movie_id 확보, 없으면 검색만
  5. DDG 비동기 검색 → RetrievedDoc 리스트로 grounding_docs 채움
  6. movie_id 있으면 movie_tmi 테이블에 INSERT

LangGraph 노드는 sync/async 둘 다 가능. 여기는 async — DDG·DB 둘 다 비동기.
chat 라우트의 graph.astream에서 자연스럽게 await됨.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.types import RetrievedDoc

if TYPE_CHECKING:
    from rag.state import QueryState


TMI_CATEGORIES = ["촬영지", "OST", "비하인드", "옥에티", "캐스팅비화"]

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "촬영지":     ["촬영", "찍은", "장소", "로케이션", "어디서"],
    "OST":        ["OST", "음악", "사운드트랙", "노래", "곡"],
    "비하인드":   ["비하인드", "제작", "에피소드", "뒷이야기", "메이킹"],
    "옥에티":     ["옥에티", "실수", "오류", "고증"],
    "캐스팅비화": ["캐스팅", "오디션", "섭외", "원래"],
}


def _pick_categories(question: str) -> list[str]:
    """질문에서 관심 카테고리 추출. 매칭 없으면 비하인드 기본."""
    matched = [
        cat
        for cat, kws in CATEGORY_KEYWORDS.items()
        if any(kw in question for kw in kws)
    ]
    return matched or ["비하인드"]


async def _resolve_movie_id(target):
    """target_movie 제목 → movies.movie_id. 없으면 None."""
    if not target:
        return None
    try:
        from db.repositories import movies_repo
        row = await movies_repo.find_by_title(target)
        return row["movie_id"] if row else None
    except Exception:
        return None


async def ground(state):
    """그라운딩 노드 — DDG 검색 + grounding_docs 채움 + DB 적재."""
    t0 = time.perf_counter()
    print("\n▶ [ground] 시작  (DuckDuckGo 실시간 검색)")

    question = state.get("question", "")
    target = state.get("target_movie")
    movie_id = await _resolve_movie_id(target)

    categories = _pick_categories(question)

    grounding_docs: list = []
    new_tmi_rows: list = []

    try:
        from ingestion.crawlers import duckduckgo_client
    except ImportError:
        return _result(state, t0, [])

    for category in categories:
        if not target:
            continue
        try:
            results = await duckduckgo_client.search_category(
                title=target,
                category=category,
                max_results=2,
            )
        except Exception:
            continue

        for r in results:
            body = (r.get("body") or "").strip()
            url = r.get("href", "")
            if not body:
                continue

            grounding_docs.append(RetrievedDoc(
                text=body,
                source="grounded",
                source_id=len(grounding_docs),
                score=0.55,
                metadata={
                    "title": target,
                    "category": category,
                    "url": url,
                    "source_url": url,
                },
            ))

            if movie_id is not None:
                new_tmi_rows.append({
                    "movie_id": movie_id,
                    "category": category,
                    "content": body,
                    "source_url": url,
                })

    if new_tmi_rows:
        try:
            from db.repositories import tmi_repo
            await tmi_repo.insert_many(new_tmi_rows)
        except Exception:
            pass

    return _result(state, t0, grounding_docs)


def _result(state, t0, grounding_docs):
    """공통 반환 셰이프."""
    latency = (time.perf_counter() - t0) * 1000
    print(f"✓ [ground] 완료 — {latency:.0f}ms  (그라운딩 문서 {len(grounding_docs)}건)")
    return {
        **state,
        "grounding_docs": grounding_docs,
        "needs_grounding": False,
        "latency_ms": {**(state.get("latency_ms") or {}), "ground": latency},
    }


__all__ = ["ground", "TMI_CATEGORIES"]
