"""
FastAPI 앱 진입점.

기존 단일 main.py(CJB)를 라우터별로 쪼개고, lifespan으로 DB 풀 관리.

실행:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

환경변수:
    SUPABASE_DB_URL=postgresql://user:pass@host/db   (또는 DB_HOST/PORT/NAME/USER/PASSWORD)
    GEMINI_API_KEY=...
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, health, movies, tmi
from core.observability import configure_langsmith
from db.client import close_pool, get_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB 풀 워밍업, 종료 시 close."""
    # LangSmith 트레이싱 — .env LANGSMITH_TRACING=true 일 때만 켜짐
    configure_langsmith()

    # DB 풀 워밍업
    try:
        await get_pool()  # 연결 실패는 첫 실제 쿼리에서 잡히게 — DB 없이도 부팅 가능
    except Exception:
        # 개발 단계에서 DB 미준비 시에도 앱은 뜨게.
        # health/db 호출 시 진짜 에러 노출됨.
        pass

    yield

    # 종료
    await close_pool()


app = FastAPI(
    title="영화 도슨트 챗봇 API",
    description="리뷰 기반 RAG 영화 가이드 챗봇 (LangGraph + Async)",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — Streamlit 로컬 개발용. 운영에서는 origin 제한 필요.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(health.router)
app.include_router(movies.router)
app.include_router(tmi.router)
app.include_router(chat.router)
