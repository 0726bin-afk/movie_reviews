"""
비동기 DB 클라이언트 — asyncpg 풀 싱글턴.

CJB의 동기 psycopg2 연결을 전면 대체. LangGraph 노드·FastAPI 라우트 모두
이 모듈의 `get_pool()`을 통해 풀에서 connection을 빌려 씀.

설계:
- pool은 첫 호출 시 1회 생성. FastAPI lifespan에서 warm-up + 종료 시 close.
- DSN 우선순위: settings.SUPABASE_DB_URL > os.environ DB_HOST/PORT/NAME/USER/PASSWORD
- min_size=2, max_size=10 — 보통 워크로드에 충분. p95 부하 보면 조정.
- pgvector 사용을 위해 connection 단위로 init 훅에서 vector 타입 등록 (선택).

사용:
    from db.client import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ...")
"""
from __future__ import annotations

import os

import asyncpg

from config.settings import settings

_pool: asyncpg.Pool | None = None


def _build_dsn() -> str:
    """
    DSN 조립 우선순위:
      1. settings.SUPABASE_DB_URL  (postgresql://user:pass@host:port/db)
      2. 환경변수 DB_HOST/PORT/NAME/USER/PASSWORD (CJB 호환)
    """
    if settings.SUPABASE_DB_URL:
        return settings.SUPABASE_DB_URL

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "postgres")
    user = os.getenv("DB_USER", "postgres")
    pw = os.getenv("DB_PASSWORD", "")
    return f"postgresql://{user}:{pw}@{host}:{port}/{name}"


async def _init_connection(conn: asyncpg.Connection) -> None:
    """
    풀에서 새 connection이 만들어질 때마다 호출되는 훅.

    Phase 4.5+에 pgvector 타입 등록 필요 시 여기에:
        from pgvector.asyncpg import register_vector
        await register_vector(conn)
    """
    # 현재는 빈 훅. 임베딩 컬럼 활용 시점에 활성화.
    return None


async def get_pool() -> asyncpg.Pool:
    """전역 connection pool 반환. 첫 호출 시 lazy 초기화."""
    global _pool
    if _pool is None:
        # DSN 주소를 변수에 담고 출력해봐
        dsn = _build_dsn()
        print(f"\n{'='*50}")
        print(f"[DB 접속 시도 주소]: {dsn}")
        print(f"{'='*50}\n")
        
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=2,
            max_size=10,
            command_timeout=30,
            init=_init_connection,
            statement_cache_size=0,
        )
    return _pool


async def close_pool() -> None:
    """앱 종료 시 호출. 풀 close + 싱글턴 리셋."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


__all__ = ["get_pool", "close_pool"]
