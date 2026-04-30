"""
CacheRepo — qa_log 테이블 위에 얹는 이중 레이어 캐시 인터페이스.

이중 레이어:
  - 레이어 1 (exact)  : 질문 텍스트 정확 일치
  - 레이어 2 (similar): 코사인 유사도 >= threshold

Phase 5: 메소드 모두 async — 노드들이 async로 전환되면서 일관성 확보.
InMemory 구현체는 await할 게 없지만 ABC 시그니처 맞추기 위해 async def.
Phase 5 후속: PostgresCacheRepo — qa_log + question_embedding 활용 (구현 완료).
"""
from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.types import Citation


@dataclass
class CachedEntry:
    """캐시 한 줄. qa_log 1 row와 1:1."""
    question: str
    answer: str
    sources: list[Citation] = field(default_factory=list)
    embedding: list[float] | None = None


class CacheRepo(ABC):
    """캐시 저장소 추상화."""

    @abstractmethod
    async def lookup_exact(self, question: str) -> CachedEntry | None: ...

    @abstractmethod
    async def lookup_similar(
        self,
        question_embedding: list[float],
        threshold: float,
    ) -> tuple[CachedEntry, float] | None: ...

    @abstractmethod
    async def save(self, entry: CachedEntry) -> None: ...


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryCacheRepo(CacheRepo):
    """프로세스 메모리 dict + list 기반 단순 구현."""

    def __init__(self) -> None:
        self._entries: list[CachedEntry] = []
        self._exact_index: dict[str, CachedEntry] = {}

    @staticmethod
    def _norm(question: str) -> str:
        return " ".join(question.split())

    async def lookup_exact(self, question: str) -> CachedEntry | None:
        return self._exact_index.get(self._norm(question))

    async def lookup_similar(
        self,
        question_embedding: list[float],
        threshold: float,
    ) -> tuple[CachedEntry, float] | None:
        best: CachedEntry | None = None
        best_score = -1.0
        for entry in self._entries:
            if entry.embedding is None:
                continue
            try:
                score = _cosine(question_embedding, entry.embedding)
            except ValueError:
                continue
            if score > best_score:
                best_score = score
                best = entry
        if best is not None and best_score >= threshold:
            return best, best_score
        return None

    async def save(self, entry: CachedEntry) -> None:
        key = self._norm(entry.question)
        if key in self._exact_index:
            old = self._exact_index[key]
            try:
                self._entries.remove(old)
            except ValueError:
                pass
        self._exact_index[key] = entry
        self._entries.append(entry)

    def __len__(self) -> int:
        return len(self._entries)


# ============================================================
# PostgresCacheRepo — Supabase qa_log 테이블 기반 영구 저장
# ============================================================

def _vec_to_str(embedding: list[float]) -> str:
    """asyncpg에 넘길 pgvector 문자열 변환. '[0.1,0.2,...]' 형식."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _serialize_sources(sources: list[Citation]) -> str | None:
    """Citation 리스트 → JSON 문자열 (qa_log.sources TEXT 컬럼)."""
    if not sources:
        return None
    return json.dumps([s.model_dump() for s in sources], ensure_ascii=False)


def _deserialize_sources(raw: str | None) -> list[Citation]:
    """JSON 문자열 → Citation 리스트."""
    if not raw:
        return []
    try:
        return [Citation(**item) for item in json.loads(raw)]
    except Exception:
        return []


class PostgresCacheRepo(CacheRepo):
    """Supabase(PostgreSQL + pgvector) 기반 캐시 저장소.

    qa_log 테이블에 읽고 씀:
      - lookup_exact  : question 텍스트 완전 일치
      - lookup_similar: question_embedding 코사인 유사도 (HNSW 인덱스)
      - save          : INSERT (중복 질문이 있어도 최신 답변 추가)
    """

    async def lookup_exact(self, question: str) -> CachedEntry | None:
        from db.client import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT question, answer, sources
                FROM qa_log
                WHERE question = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                question,
            )
        if row is None:
            return None
        return CachedEntry(
            question=row["question"],
            answer=row["answer"],
            sources=_deserialize_sources(row["sources"]),
        )

    async def lookup_similar(
        self,
        question_embedding: list[float],
        threshold: float,
    ) -> tuple[CachedEntry, float] | None:
        from db.client import get_pool
        pool = await get_pool()
        vec_str = _vec_to_str(question_embedding)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT question, answer, sources,
                       1 - (question_embedding <=> $1::vector) AS score
                FROM qa_log
                WHERE question_embedding IS NOT NULL
                ORDER BY question_embedding <=> $1::vector
                LIMIT 1
                """,
                vec_str,
            )
        if row is None:
            return None
        score = float(row["score"])
        if score < threshold:
            return None
        entry = CachedEntry(
            question=row["question"],
            answer=row["answer"],
            sources=_deserialize_sources(row["sources"]),
        )
        return entry, score

    async def save(self, entry: CachedEntry) -> None:
        from db.client import get_pool
        pool = await get_pool()
        sources_json = _serialize_sources(entry.sources)

        async with pool.acquire() as conn:
            if entry.embedding is not None:
                await conn.execute(
                    """
                    INSERT INTO qa_log (question, answer, sources, question_embedding)
                    VALUES ($1, $2, $3, $4::vector)
                    """,
                    entry.question,
                    entry.answer,
                    sources_json,
                    _vec_to_str(entry.embedding),
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO qa_log (question, answer, sources)
                    VALUES ($1, $2, $3)
                    """,
                    entry.question,
                    entry.answer,
                    sources_json,
                )


_default_repo: CacheRepo | None = None


def get_cache_repo() -> CacheRepo:
    """캐시 저장소 싱글턴.
    PostgresCacheRepo(Supabase qa_log)를 사용.
    DB 연결 없이 테스트할 때는 reset_cache_repo() 후 InMemoryCacheRepo를 직접 주입."""
    global _default_repo
    if _default_repo is None:
        _default_repo = PostgresCacheRepo()
    return _default_repo


def reset_cache_repo() -> None:
    """테스트용."""
    global _default_repo
    _default_repo = None


__all__ = [
    "CacheRepo",
    "CachedEntry",
    "InMemoryCacheRepo",
    "PostgresCacheRepo",
    "get_cache_repo",
    "reset_cache_repo",
]
