"""
SelfQueryRetriever — 자연어 질문을 메타데이터 필터 + 시맨틱 쿼리로 분리해
pgvector 코사인 검색으로 review_embeddings에서 top-k 리뷰 반환.

설계 (옵션 A: 하이브리드):
  - LLM (Gemini) 구조화 출력으로 자연어 → {filters, semantic_query} 추출
  - 실제 검색은 asyncpg로 직접 SQL — schema의 review_embeddings 구조에 맞춰 작성
  - LangChain의 SelfQueryRetriever 표준 wrapper는 schema(JSONB metadata 부재)와 안 맞아 사용 안 함

검색 결과는 RetrievedDoc 리스트로 반환 — retrieve.py가 그대로 state.retrieved_docs에 박음.

지원하는 메타데이터 필터:
  - movie_id (정수)
  - title (문자열, 정확 일치)
  - rating_min / rating_max (실수 범위)
  - likes_min (정수, 인기 리뷰만)
  - genre (문자열 substring 매치)
  - director (문자열 정확 일치)

후속 (Phase 5+):
  - Gemini structured output (`with_structured_output`)으로 필터 추출 정확도↑
  - HNSW 인덱스 활용 (현재 schema는 IVFFlat 주석. 실제 운영 시 활성화)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from core.types import RetrievedDoc
from db.client import get_pool
from langchain_core.prompts import ChatPromptTemplate
from providers.embedding import get_embedding
from providers.llm import get_llm


# ============================================================
# 필터 파싱 — 자연어 → 구조화된 SQL WHERE 절 후보
# ============================================================

@dataclass
class QueryFilters:
    """질문에서 추출된 메타데이터 필터.
    None은 '필터 없음'."""
    movie_id: int | None = None
    title: str | None = None
    rating_min: float | None = None
    rating_max: float | None = None
    likes_min: int | None = None
    genre: str | None = None
    director: str | None = None
    # 의미 검색에 쓸 정제된 쿼리 (필터 단어들 제거된 핵심 의미)
    semantic_query: str = ""


# 필터 추출 프롬프트 — JSON 출력 강제
FILTER_PROMPT_TEMPLATE = """\
사용자 질문에서 영화 검색 메타데이터 필터를 추출해 JSON으로만 답하세요.

[추출 가능 필드]
- title: 영화 제목 (정확히 언급된 경우만)
- rating_min / rating_max: 별점 범위 (0.0~5.0)
- likes_min: 좋아요 최소치 (인기 리뷰만 보고 싶을 때)
- genre: 장르 (드라마, 액션, 스릴러 등)
- director: 감독 이름
- semantic_query: 메타데이터 단어 빼고 남은 핵심 의미 (예: "연기가 좋은 부분", "반전 스포")

[규칙]
- 명시되지 않은 필드는 null
- semantic_query는 항상 채움 (질문 그대로여도 OK)
- JSON만 출력, 다른 텍스트 금지

[예시]
질문: "기생충 4점 이상 리뷰에서 연기에 대한 평가 알려줘"
출력: {{"title": "기생충", "rating_min": 4.0, "rating_max": null, "likes_min": null, "genre": null, "director": null, "semantic_query": "연기에 대한 평가"}}

질문: "봉준호 감독 영화 중 호불호 갈리는 거"
출력: {{"title": null, "rating_min": null, "rating_max": null, "likes_min": null, "genre": null, "director": "봉준호", "semantic_query": "호불호 갈리는 부분"}}

질문: "스릴러 장르에서 연출 좋은 영화"
출력: {{"title": null, "rating_min": null, "rating_max": null, "likes_min": null, "genre": "스릴러", "director": null, "semantic_query": "연출 좋은 부분"}}

[질문]
{question}

[JSON]"""

filter_prompt = ChatPromptTemplate.from_template(FILTER_PROMPT_TEMPLATE)


async def extract_filters(question: str, target_movie: str | None = None) -> QueryFilters:
    """LLM에게 질문에서 필터를 뽑게 시킴. 실패하면 빈 필터 + 원문 semantic_query."""
    llm = get_llm()
    try:
        prompt_value = filter_prompt.format_prompt(question=question)
        raw = await llm.ainvoke(prompt_value.to_string())
        # JSON만 추출 (마크다운 코드블록 등 제거)
        raw = raw.strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return QueryFilters(title=target_movie, semantic_query=question)
        data = json.loads(m.group(0))
        title = data.get("title") or target_movie
        return QueryFilters(
            title=title,
            rating_min=_to_float(data.get("rating_min")),
            rating_max=_to_float(data.get("rating_max")),
            likes_min=_to_int(data.get("likes_min")),
            genre=data.get("genre"),
            director=data.get("director"),
            semantic_query=data.get("semantic_query") or question,
        )
    except Exception:
        # LLM 실패 — 필터 없이 시맨틱 검색만
        return QueryFilters(title=target_movie, semantic_query=question)


def _to_float(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v) -> int | None:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


# ============================================================
# 검색 본체
# ============================================================

async def search(
    question: str,
    target_movie: str | None = None,
    top_k: int = 6,
) -> list[RetrievedDoc]:
    """
    Self-query 검색의 외부 진입점.

    1) Gemini로 자연어 → 필터 + semantic_query 분리
    2) semantic_query 임베딩
    3) review_embeddings JOIN movies로 코사인 유사도 + 필터 검색
    4) RetrievedDoc 리스트 반환

    Args:
        question: 사용자 원본 질문
        target_movie: route_query가 추출한 영화 제목 (있으면 movie_id 필터 우선 적용)
        top_k: 반환할 문서 수
    """
    filters = await extract_filters(question, target_movie=target_movie)

    # 시맨틱 임베딩
    try:
        qe = await get_embedding().aembed_query(filters.semantic_query)
    except Exception:
        return []

    # title이 있으면 movie_id로 변환 (정확 매칭, 없어도 검색은 진행)
    movie_id = await _resolve_movie_id(filters.title)

    return await _vector_search(
        question_embedding=qe,
        movie_id=movie_id,
        filters=filters,
        top_k=top_k,
    )


async def _resolve_movie_id(title: str | None) -> int | None:
    if not title:
        return None
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT movie_id FROM movies WHERE title = $1 LIMIT 1",
            title,
        )
        return row["movie_id"] if row else None


async def _vector_search(
    question_embedding: list[float],
    movie_id: int | None,
    filters: QueryFilters,
    top_k: int,
) -> list[RetrievedDoc]:
    """
    review_embeddings JOIN movies로 코사인 검색 + 메타 필터.

    pgvector 코사인 거리: `<=>` 연산자 (낮을수록 유사). similarity = 1 - distance.
    """
    where_clauses: list[str] = []
    params: list = []

    def add(cond: str, value):
        params.append(value)
        where_clauses.append(cond.format(idx=len(params)))

    if movie_id is not None:
        add("re.movie_id = ${idx}", movie_id)
    if filters.rating_min is not None:
        add("re.rating >= ${idx}", filters.rating_min)
    if filters.rating_max is not None:
        add("re.rating <= ${idx}", filters.rating_max)
    if filters.likes_min is not None:
        add("re.likes >= ${idx}", filters.likes_min)
    if filters.genre:
        # genre는 콤마 구분 문자열 — substring 매치
        add("m.genre ILIKE ${idx}", f"%{filters.genre}%")
    if filters.director:
        add("m.director ILIKE ${idx}", f"%{filters.director}%")

    # pgvector는 list를 string으로 변환해서 ::vector 캐스팅
    embedding_literal = "[" + ",".join(f"{x:.7f}" for x in question_embedding) + "]"
    params.append(embedding_literal)
    embedding_idx = len(params)
    params.append(top_k)
    limit_idx = len(params)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = f"""
        SELECT
            re.review_id,
            re.movie_id,
            re.content,
            re.rating,
            re.likes,
            re.movie_nm,
            m.title,
            m.director,
            m.genre,
            m.release_date,
            1 - (re.embedding <=> ${embedding_idx}::vector) AS similarity
        FROM review_embeddings re
        LEFT JOIN movies m ON re.movie_id = m.movie_id
        {where_sql}
        ORDER BY re.embedding <=> ${embedding_idx}::vector
        LIMIT ${limit_idx}
    """

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    docs: list[RetrievedDoc] = []
    for r in rows:
        docs.append(RetrievedDoc(
            text=r["content"],
            source="review",
            source_id=r["review_id"],
            score=float(r["similarity"]) if r["similarity"] is not None else 0.0,
            metadata={
                "title": r["title"] or r["movie_nm"],
                "movie_id": r["movie_id"],
                "director": r["director"],
                "genre": r["genre"],
                "rating": float(r["rating"]) if r["rating"] is not None else None,
                "likes_count": r["likes"],
                "release_date": str(r["release_date"]) if r["release_date"] else None,
            },
        ))
    return docs


__all__ = ["search", "extract_filters", "QueryFilters"]
