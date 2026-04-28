"""
CacheRepo — qa_log 테이블 위에 얹는 이중 레이어 캐시 인터페이스.

기획안 §4.1 이중 레이어 캐시:
  - 레이어 1 (exact)  : 질문 텍스트 정확 일치 — 즉시 반환
  - 레이어 2 (similar): 질문 임베딩 코사인 유사도 ≥ threshold — 같은 의미 질문 재사용

설계 원칙:
- 노드는 이 인터페이스만 알고, 구현체는 팩토리(`get_cache_repo()`)에서 받음
- Phase 4 현재: in-memory 구현체로 인터페이스만 박아둠 — 프로세스 재시작 시 캐시 휘발
- Phase 4.5: CJB가 qa_log + embedding 컬럼 추가하면 PostgresCacheRepo로 교체

CJB가 schema 보강할 항목 (회의 결과 따라):
  ALTER TABLE qa_log ADD COLUMN question_embedding vector(768);
  ALTER TABLE qa_log ADD COLUMN sources_json JSONB;  -- Citation 직렬화용
  CREATE INDEX ON qa_log USING hnsw (question_embedding vector_cosine_ops);
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.types import Citation


# ============================================================
# 데이터 단위
# ============================================================

@dataclass
class CachedEntry:
    """캐시 한 줄. qa_log 테이블 1 row와 1:1."""
    question: str
    answer: str
    sources: list[Citation] = field(default_factory=list)
    embedding: list[float] | None = None  # 레이어 2 매칭용


# ============================================================
# CacheRepo ABC
# ============================================================

class CacheRepo(ABC):
    """캐시 저장소 추상화. 구현체는 in-memory 또는 PostgreSQL backed."""

    @abstractmethod
    def lookup_exact(self, question: str) -> CachedEntry | None:
        """레이어 1: 질문 문자열 정확 일치. 가장 빠른 경로."""
        ...

    @abstractmethod
    def lookup_similar(
        self,
        question_embedding: list[float],
        threshold: float,
    ) -> tuple[CachedEntry, float] | None:
        """
        레이어 2: 코사인 유사도 ≥ threshold인 가장 가까운 entry 반환.
        반환값의 두 번째 요소는 매칭 점수 (디버깅·로깅용).
        매칭 없으면 None.
        """
        ...

    @abstractmethod
    def save(self, entry: CachedEntry) -> None:
        """새 캐시 저장. 동일 질문이 이미 있으면 덮어씀 또는 무시 (구현체 자유)."""
        ...


# ============================================================
# In-memory 구현 (Phase 4 임시)
# ============================================================

def _cosine(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도. 길이 다르면 ValueError."""
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryCacheRepo(CacheRepo):
    """
    프로세스 메모리 dict + list 기반 단순 구현.

    한계:
    - 재시작 시 사라짐
    - lookup_similar이 O(N) 선형 탐색 — 캐시 100개 미만에서만 의미
    - 동시성 미지원 (단일 프로세스 가정)

    Phase 4.5에서 PostgresCacheRepo로 교체 — 그땐 pgvector HNSW 인덱스로 ANN 검색.
    """

    def __init__(self) -> None:
        self._entries: list[CachedEntry] = []
        self._exact_index: dict[str, CachedEntry] = {}

    @staticmethod
    def _norm(question: str) -> str:
        """exact 매칭 키 — 양끝 공백·연속 공백 정규화."""
        return " ".join(question.split())

    def lookup_exact(self, question: str) -> CachedEntry | None:
        return self._exact_index.get(self._norm(question))

    def lookup_similar(
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
                continue  # 차원 다른 임베딩(모델 교체 직후)은 무시
            if score > best_score:
                best_score = score
                best = entry
        if best is not None and best_score >= threshold:
            return best, best_score
        return None

    def save(self, entry: CachedEntry) -> None:
        key = self._norm(entry.question)
        if key in self._exact_index:
            # 동일 질문 재방문: 최신 답으로 갱신
            old = self._exact_index[key]
            try:
                self._entries.remove(old)
            except ValueError:
                pass
        self._exact_index[key] = entry
        self._entries.append(entry)

    # 디버깅용
    def __len__(self) -> int:
        return len(self._entries)


# ============================================================
# 팩토리
# ============================================================

_default_repo: CacheRepo | None = None


def get_cache_repo() -> CacheRepo:
    """캐시 저장소 싱글턴.
    Phase 4 현재: InMemoryCacheRepo.
    Phase 4.5: settings.APP_ENV 또는 CJB의 cache_repo.py에 따라 PostgresCacheRepo 교체.
    """
    global _default_repo
    if _default_repo is None:
        _default_repo = InMemoryCacheRepo()
    return _default_repo


def reset_cache_repo() -> None:
    """테스트용 — 싱글턴 리셋."""
    global _default_repo
    _default_repo = None


__all__ = [
    "CacheRepo",
    "CachedEntry",
    "InMemoryCacheRepo",
    "get_cache_repo",
    "reset_cache_repo",
]
