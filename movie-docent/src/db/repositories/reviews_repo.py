"""
reviews 테이블 비동기 CRUD.

CJB schema.sql 기준:
  review_id (PK), movie_id (FK), reviewer_nickname, rating, likes_count,
  comments_count, content, sort_type, collected_at
"""
from __future__ import annotations

from db.client import get_pool


async def get_top_reviews(movie_id: int, limit: int = 10) -> list[dict]:
    """좋아요 많은 순 상위 N개. 영화 상세 페이지·기본 retrieve용."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT review_id, reviewer_nickname, rating, likes_count, content
            FROM reviews
            WHERE movie_id = $1
            ORDER BY likes_count DESC
            LIMIT $2
            """,
            movie_id,
            limit,
        )
        return [dict(r) for r in rows]


async def get_reviews_by_rating(
    movie_id: int,
    min_rating: float | None = None,
    max_rating: float | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    평점 범위 필터.

    polarity 분기에서 사용:
      - 호평 측: min_rating=4.0
      - 혹평 측: max_rating=2.0
    """
    pool = await get_pool()
    where = ["movie_id = $1"]
    params: list = [movie_id]

    if min_rating is not None:
        where.append(f"rating >= ${len(params) + 1}")
        params.append(min_rating)
    if max_rating is not None:
        where.append(f"rating <= ${len(params) + 1}")
        params.append(max_rating)

    sql = f"""
        SELECT review_id, reviewer_nickname, rating, likes_count, content
        FROM reviews
        WHERE {' AND '.join(where)}
        ORDER BY likes_count DESC
        LIMIT ${len(params) + 1}
    """
    params.append(limit)

    async with await get_pool() as _:
        pass  # noop — 패턴 일관성용
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]


async def count_reviews(movie_id: int) -> int:
    """영화당 리뷰 수. 통계용."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM reviews WHERE movie_id = $1",
            movie_id,
        )


__all__ = ["get_top_reviews", "get_reviews_by_rating", "count_reviews"]
