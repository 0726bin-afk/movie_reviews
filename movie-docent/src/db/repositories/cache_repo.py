"""
CacheRepo — qa_log 테이블 위에 얹는 이중 레이어 캐시 인터페이스.

이중 레이어:
  - 레이어 1 (exact)  : 질문 텍스트 정확 일치
  - 레이어 2 (similar): 코사인 유사도 >= threshold

Phase 5: 메소드 모두 async — 노드들이 async로 전환되면서 일관성 확보.
InMemory 구현체는 await할 게 없지만 ABC 시그니처 맞추기 위해 async def.
Phase 5 후속: PostgresCacheRepo가 같은 ABC 구현 — qa_log + question_embedding 활용.
"""
from __future__ import annotations

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


_default_repo: CacheRepo | None = None


def get_cache_repo() -> CacheRepo:
    """캐시 저장소 싱글턴.
    Phase 5 현재: InMemoryCacheRepo.
    Phase 5 후속: PostgresCacheRepo로 라우팅."""
    global _default_repo
    if _default_repo is None:
        _default_repo = InMemoryCacheRepo()
    return _default_repo


def reset_cache_repo() -> None:
    """테스트용."""
    global _default_repo
    _default_repo = None


__all__ = [
    "CacheRepo",
    "CachedEntry",
    "InMemoryCacheRepo",
    "get_cache_repo",
    "reset_cache_repo",
]
