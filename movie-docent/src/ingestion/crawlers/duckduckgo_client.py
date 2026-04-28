"""
DuckDuckGo 검색 클라이언트 — TMI 그라운딩용.

비동기 코드 안에서 동기 DDGS를 안전하게 쓰기 위해 `asyncio.to_thread`로 격리.
LangGraph ground 노드와 FastAPI /grounding 라우트가 이 모듈을 공유.

CJB main.py의 검색어 템플릿을 그대로 가져와 일관성 유지.
"""
from __future__ import annotations

import asyncio


# CJB main.py에서 가져온 카테고리별 검색어 템플릿
TMI_QUERY_TEMPLATES: dict[str, str] = {
    "촬영지":     "{title} 영화 촬영지",
    "OST":        "{title} 영화 OST 음악",
    "비하인드":   "{title} 영화 제작 비하인드 비화",
    "옥에티":     "{title} 영화 옥에티 실수",
    "캐스팅비화": "{title} 영화 캐스팅 비화",
}


def _sync_search(query: str, max_results: int) -> list[dict]:
    """동기 DDG 호출. asyncio.to_thread로 감싸서 비동기 컨텍스트에서 사용."""
    # 의존성은 옵션 그룹에 있음 — 사용 시점에 import.
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, region="kr-kr", max_results=max_results))


async def search(query: str, max_results: int = 3) -> list[dict]:
    """비동기 래퍼. 이벤트 루프 블로킹 방지."""
    return await asyncio.to_thread(_sync_search, query, max_results)


async def search_category(
    title: str,
    category: str,
    max_results: int = 3,
) -> list[dict]:
    """카테고리별 TMI 검색. 결과는 [{title, body, href, ...}, ...]."""
    template = TMI_QUERY_TEMPLATES.get(category)
    if not template:
        raise ValueError(f"Unknown TMI category: {category!r}")
    query = template.format(title=title)
    return await search(query, max_results=max_results)


__all__ = ["TMI_QUERY_TEMPLATES", "search", "search_category"]
