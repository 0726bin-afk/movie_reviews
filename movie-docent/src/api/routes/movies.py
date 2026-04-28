"""
영화 목록·상세 조회 라우터.

CJB main.py의 /movies, /movies/{movie_id} 엔드포인트를 비동기로 이식.
DB 쿼리는 db/repositories/movies_repo, reviews_repo, tmi_repo로 위임.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from db.repositories import movies_repo, reviews_repo, tmi_repo

router = APIRouter(tags=["영화"])


@router.get("/movies")
async def get_movies() -> dict:
    """영화 목록 — Streamlit 사이드바 드롭다운용."""
    movies = await movies_repo.list_movies()
    return {"count": len(movies), "movies": movies}


@router.get("/movies/{movie_id}")
async def get_movie_detail(movie_id: int) -> dict:
    """영화 1건 상세 + 인기 리뷰 + TMI."""
    movie = await movies_repo.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="영화를 찾을 수 없어요.")

    reviews = await reviews_repo.get_top_reviews(movie_id, limit=10)
    tmi = await tmi_repo.list_tmi(movie_id)

    return {
        "movie": movie,
        "top_reviews": reviews,
        "tmi": tmi,
    }
