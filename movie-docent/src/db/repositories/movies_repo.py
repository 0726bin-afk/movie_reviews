"""
movies 테이블 비동기 CRUD.

CJB schema.sql 기준 컬럼명 사용:
  movie_id (PK), title, genre, director, release_date, tmdb_rating, tmdb_id, cast_members
"""
from __future__ import annotations

from db.client import get_pool


async def list_movies() -> list[dict]:
    """전체 영화 목록 — Streamlit 사이드바·드롭다운용."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT movie_id, title, genre, director, release_date, tmdb_rating
            FROM movies
            ORDER BY movie_id
            """
        )
        return [dict(r) for r in rows]


async def get_movie(movie_id: int) -> dict | None:
    """영화 1건 상세."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM movies WHERE movie_id = $1",
            movie_id,
        )
        return dict(row) if row else None


async def get_movie_title(movie_id: int) -> str | None:
    """movie_id → title 빠른 조회. 그라운딩 검색어 조립용."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT title FROM movies WHERE movie_id = $1",
            movie_id,
        )
        return row["title"] if row else None


async def find_by_title(title: str) -> dict | None:
    """제목 정확 일치로 1건 — route_query에서 추출한 target_movie 매핑용."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM movies WHERE title = $1 LIMIT 1",
            title,
        )
        return dict(row) if row else None


__all__ = ["list_movies", "get_movie", "get_movie_title", "find_by_title"]
