"""
TMI 조회 + 운영 도구로서의 그라운딩 라우터.

`/tmi/{movie_id}` — DB에 적재된 TMI 조회 (CJB main.py와 동일 인터페이스)
`/grounding`     — 운영자가 수동으로 카테고리별 DDG 검색 + DB 적재 트리거

LangGraph 안에서의 그라운딩은 rag/nodes/ground.py가 담당. 이 라우트는
'관리자가 미리 채우는' 용도이고, 둘 다 같은 ingestion/crawlers + tmi_repo 사용.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.repositories import movies_repo, tmi_repo
from ingestion.crawlers import duckduckgo_client

router = APIRouter(tags=["TMI"])


class GroundingRequest(BaseModel):
    movie_id: int
    category: str  # 촬영지 / OST / 비하인드 / 옥에티 / 캐스팅비화


@router.get("/tmi/{movie_id}")
async def get_tmi(movie_id: int, category: str | None = None) -> dict:
    """영화 TMI 조회. category 쿼리 파라미터로 필터 가능."""
    tmi = await tmi_repo.list_tmi(movie_id, category=category)
    return {"movie_id": movie_id, "count": len(tmi), "tmi": tmi}


@router.post("/grounding")
async def run_grounding(req: GroundingRequest) -> dict:
    """
    운영자가 수동 트리거하는 그라운딩.
    DDG 검색 → 결과를 movie_tmi 테이블에 적재.

    LangGraph 안의 ground 노드와 동일한 ingestion 모듈을 공유하므로
    동작 일관성 보장.
    """
    title = await movies_repo.get_movie_title(req.movie_id)
    if not title:
        raise HTTPException(status_code=404, detail="영화를 찾을 수 없어요.")

    try:
        results = await duckduckgo_client.search_category(
            title=title,
            category=req.category,
            max_results=3,
        )
    except ValueError as e:
        # 알 수 없는 카테고리
        raise HTTPException(status_code=400, detail=str(e))

    rows = [
        {
            "movie_id": req.movie_id,
            "category": req.category,
            "content": (r.get("body") or "").strip(),
            "source_url": r.get("href", ""),
        }
        for r in results
        if (r.get("body") or "").strip()
    ]
    saved = await tmi_repo.insert_many(rows)

    # rate limit 완화 — CJB main.py에서 가져옴
    await asyncio.sleep(1)

    return {
        "message": f"'{req.category}' 그라운딩 완료",
        "saved": saved,
    }
