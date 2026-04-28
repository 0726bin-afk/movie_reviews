"""
retrieve 노드 — 질문에 관련된 문서 검색.

Phase 3 현재: fake retriever — fixture 파일에서 영화 정보 + 리뷰 N건 반환.
Phase 3.5: `rag.retrievers.self_query.SelfQueryRetriever`로 교체
          (DB + pgvector + Gemini Self-Query 메타데이터 필터)

state -> state 시그니처.
입력: question, target_movie (옵션), query_type (옵션)
출력: retrieved_docs (+ latency_ms 갱신)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.types import RetrievedDoc

if TYPE_CHECKING:
    from rag.state import QueryState


# ============================================================
# Fixture 경로 — repo root / tests / fixtures / sample_reviews.json
# ============================================================
# __file__ → .../src/rag/nodes/retrieve.py
# parents[0]=nodes, [1]=rag, [2]=src, [3]=movie-docent (repo root)
FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sample_reviews.json"
)


def _load_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(
            f"Fixture not found: {FIXTURE_PATH}\n"
            f"Phase 3 retrieve는 fixture에 의존. tests/fixtures/sample_reviews.json 확인."
        )
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _fake_search(question: str, target_movie: str | None = None) -> list[RetrievedDoc]:
    """
    Fixture에서 movie + reviews를 RetrievedDoc 리스트로 반환.

    Phase 3.5에서 이 함수 자리에 self-query retriever 호출이 들어옴.
    질문 내용 무관하게 fixture를 그대로 반환 (검색 품질은 Phase 3.5+ 작업).
    """
    data = _load_fixture()
    movie = data["movie"]
    reviews = data["reviews"]

    docs: list[RetrievedDoc] = []

    # ---- 영화 정보 doc ----
    movie_text = (
        f"{movie['title']} — 감독 {movie['director']}, "
        f"개봉 {movie['release_date']}, 장르 {movie['genre']}. "
        f"출연: {movie['cast_members']}. "
        f"줄거리: {movie['overview']}"
    )
    docs.append(RetrievedDoc(
        text=movie_text,
        source="movie",
        source_id=movie["movie_id"],
        score=1.0,
        metadata={
            "title": movie["title"],
            "director": movie["director"],
            "release_date": movie["release_date"],
            "tmdb_rating": movie.get("tmdb_rating"),
        },
    ))

    # ---- 리뷰 docs ----
    for r in reviews:
        docs.append(RetrievedDoc(
            text=r["content"],
            source="review",
            source_id=r["review_id"],
            score=0.85,  # fake score
            metadata={
                "title": movie["title"],
                "reviewer_nickname": r["reviewer_nickname"],
                "rating": r["rating"],
                "likes_count": r["likes_count"],
            },
        ))

    return docs


def retrieve(state: "QueryState") -> "QueryState":
    """질문 → 관련 문서 리스트."""
    t0 = time.perf_counter()

    question = state.get("question", "")
    target = state.get("target_movie")

    docs = _fake_search(question, target_movie=target)

    latency = (time.perf_counter() - t0) * 1000
    return {
        **state,
        "retrieved_docs": docs,
        "latency_ms": {**(state.get("latency_ms") or {}), "retrieve": latency},
    }
