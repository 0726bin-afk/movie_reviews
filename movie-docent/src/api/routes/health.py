"""헬스 체크 라우터 — uvicorn 떠 있는지·DB 풀 살아있는지."""
from __future__ import annotations

from fastapi import APIRouter

from db.client import get_pool

router = APIRouter(tags=["서버"])


@router.get("/health")
async def health_check() -> dict:
    """단순 ping."""
    return {"status": "ok", "message": "서버 정상 작동 중"}


@router.get("/health/db")
async def health_db() -> dict:
    """DB 연결까지 확인하는 깊은 체크 — 운영 모니터링용."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    return {"status": "ok" if result == 1 else "degraded", "db": "reachable"}
