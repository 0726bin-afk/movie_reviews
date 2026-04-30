"""
retrieve 노드 — 질문에 관련된 문서 검색.

Phase 5: query_type별로 적합한 소스를 다르게 선택.

  basic_info     -> movies + 인기 리뷰 3건
  review_summary -> self_query (review_embeddings)
  polarity       -> self_query
  tmi            -> movie_tmi 테이블
  recommendation -> self_query

DB 연결 실패·schema 미준비 시: 빈 리스트 반환. 그래프 멈추지 않음.
state -> state. async.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from config.settings import settings
from core.types import RetrievedDoc

if TYPE_CHECKING:
    from rag.state import QueryState


async def _retrieve_basic_info(target_movie):
    """basic_info: 영화 메타 1건 + 인기 리뷰 3건."""
    if not target_movie:
        return []

    from db.repositories import movies_repo, reviews_repo

    movie = await movies_repo.find_by_title(target_movie)
    if not movie:
        return []

    docs = []

    overview = movie.get("overview") or ""
    movie_text = (
        f"{movie['title']} — 감독 {movie.get('director') or '?'}, "
        f"개봉 {movie.get('release_date') or '?'}, "
        f"장르 {movie.get('genre') or '?'}. "
        f"출연: {movie.get('cast_members') or '?'}. "
        f"줄거리: {overview}"
    )
    docs.append(RetrievedDoc(
        text=movie_text,
        source="movie",
        source_id=movie["movie_id"],
        score=1.0,
        metadata={
            "title": movie["title"],
            "director": movie.get("director"),
            "release_date": str(movie.get("release_date")) if movie.get("release_date") else None,
            "genre": movie.get("genre"),
            "tmdb_rating": float(movie["tmdb_rating"]) if movie.get("tmdb_rating") else None,
        },
    ))

    reviews = await reviews_repo.get_top_reviews(movie["movie_id"], limit=3)
    for r in reviews:
        docs.append(RetrievedDoc(
            text=r["content"],
            source="review",
            source_id=r["review_id"],
            score=0.7,
            metadata={
                "title": movie["title"],
                "reviewer_nickname": r.get("reviewer_nickname"),
                "rating": float(r["rating"]) if r.get("rating") else None,
                "likes_count": r.get("likes_count"),
            },
        ))
    return docs


async def _retrieve_via_self_query(question, target_movie, top_k):
    """review_summary / polarity / recommendation 공통 — self_query 사용."""
    try:
        from rag.retrievers import self_query
        return await self_query.search(
            question=question,
            target_movie=target_movie,
            top_k=top_k,
        )
    except Exception:
        return []


async def _retrieve_tmi(target_movie):
    """tmi: movie_tmi 테이블 SELECT. 결과 0건이면 graph가 ground로 라우팅."""
    if not target_movie:
        return []

    from db.repositories import movies_repo, tmi_repo

    movie = await movies_repo.find_by_title(target_movie)
    if not movie:
        return []

    rows = await tmi_repo.list_tmi(movie["movie_id"])
    docs = []
    for row in rows:
        docs.append(RetrievedDoc(
            text=row["content"],
            source="tmi",
            source_id=row["tmi_id"],
            score=0.9,
            metadata={
                "title": movie["title"],
                "category": row["category"],
                "source_url": row.get("source_url"),
            },
        ))
    return docs


async def retrieve(state):
    """query_type 분기 → 적합한 소스 검색."""
    t0 = time.perf_counter()

    question = state.get("question", "")
    target = state.get("target_movie")
    query_type = state.get("query_type") or "basic_info"
    top_k = settings.RETRIEVER_TOP_K

    print(f"\n[DEBUG] 현재 추출된 영화 제목: '{target}'")
    print(f"[DEBUG] 현재 판별된 쿼리 타입: {query_type}")

    try:
        if query_type == "basic_info":
            docs = await _retrieve_basic_info(target)
            if not docs:
                docs = await _retrieve_via_self_query(question, target, top_k)
        elif query_type in ("review_summary", "polarity"):
            docs = await _retrieve_via_self_query(question, target, top_k)
        elif query_type == "tmi":
            docs = await _retrieve_tmi(target)
        elif query_type == "recommendation":
            docs = await _retrieve_via_self_query(question, None, top_k)
        else:
            docs = await _retrieve_via_self_query(question, target, top_k)
    except Exception:
        docs = []

    latency = (time.perf_counter() - t0) * 1000
    return {
        **state,
        "retrieved_docs": docs,
        "latency_ms": {**(state.get("latency_ms") or {}), "retrieve": latency},
    }
