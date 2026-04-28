"""
movie_tmi 테이블 비동기 CRUD.

CJB schema.sql 기준:
  tmi_id (PK), movie_id (FK), category, content, source_url, created_at

ground 노드와 /grounding 라우트가 INSERT, /tmi/{id}와 retrieve가 SELECT.
"""
from __future__ import annotations

from db.client import get_pool


async def list_tmi(movie_id: int, category: str | None = None) -> list[dict]:
    """
    영화의 TMI 목록.
    category가 주어지면 해당 카테고리만, 없으면 전체.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category:
            rows = await conn.fetch(
                """
                SELECT tmi_id, category, content, source_url, created_at
                FROM movie_tmi
                WHERE movie_id = $1 AND category = $2
                """,
                movie_id,
                category,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT tmi_id, category, content, source_url, created_at
                FROM movie_tmi
                WHERE movie_id = $1
                ORDER BY category
                """,
                movie_id,
            )
        return [dict(r) for r in rows]


async def has_category(movie_id: int, category: str) -> bool:
    """해당 영화에 이 카테고리 TMI가 1건 이상 있는지 — 그라운딩 스킵 판단."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM movie_tmi WHERE movie_id = $1 AND category = $2",
            movie_id,
            category,
        )
        return cnt > 0


async def insert_many(items: list[dict]) -> int:
    """
    여러 TMI 일괄 INSERT.

    Args:
        items: [{movie_id, category, content, source_url}, ...]

    Returns:
        실제 INSERT된 행 수.
    """
    if not items:
        return 0

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO movie_tmi (movie_id, category, content, source_url)
            VALUES ($1, $2, $3, $4)
            """,
            [
                (
                    i["movie_id"],
                    i["category"],
                    i["content"],
                    i.get("source_url", ""),
                )
                for i in items
            ],
        )
    return len(items)


__all__ = ["list_tmi", "has_category", "insert_many"]
