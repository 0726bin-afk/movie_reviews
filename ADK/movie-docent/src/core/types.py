"""
프로젝트 전역 도메인 타입.

DB 테이블, API 응답, RAG 노드 — 모든 레이어가 공유하는 데이터 모양.
이 모듈은 다른 어떤 모듈도 import하지 않는다 (의존성 진앙지).

Pydantic v2 기준.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Enums
# ============================================================

class Genre(str, Enum):
    """장르 분류. TMDB 장르 코드와 매핑되는 한국어 명."""
    SF = "SF"
    ACTION = "액션"
    THRILLER = "스릴러"
    DRAMA = "드라마"
    ANIMATION = "애니메이션"
    HERO = "히어로"
    FANTASY = "판타지"
    HORROR = "공포"
    COMEDY = "코미디"
    ROMANCE = "로맨스"
    DOCUMENTARY = "다큐멘터리"
    REAL_BASED = "실화기반"
    OTHER = "기타"


class TMICategory(str, Enum):
    """TMI 카테고리. 기획안 §3.2."""
    LOCATION = "촬영지"
    CASTING = "캐스팅비화"
    OST = "OST"
    BLOOPER = "옥에티"
    PRODUCTION = "제작일화"
    CULTURAL = "문화맥락"
    OTHER = "기타"


class ReviewSentiment(str, Enum):
    """리뷰 호불호 분류. 평점 기반 자동 분류 + 태깅 결과 결합."""
    POSITIVE = "positive"   # 평점 >= 4
    NEUTRAL = "neutral"     # 평점 == 3
    NEGATIVE = "negative"   # 평점 <= 2


# ============================================================
# Domain Models
# ============================================================

class Movie(BaseModel):
    """
    영화 메타데이터. TMDB API + 보강 정보.

    `is_polarizing` / `is_complex` / `has_rich_tmi` 세 플래그는
    기획안 §2.4 난이도 분류 축. 시드 데이터 단계에서 수동 표기.
    eval 단계에서 "난이도군 정확도 70% 이상" 측정에 직접 사용됨.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int                                   # TMDB ID 사용 권장
    title: str                                # 한국어 제목
    original_title: Optional[str] = None
    director: Optional[str] = None
    cast: list[str] = Field(default_factory=list)
    genres: list[Genre] = Field(default_factory=list)
    overview: Optional[str] = None            # 줄거리
    release_date: Optional[date] = None
    runtime_min: Optional[int] = None
    poster_url: Optional[str] = None
    rating_avg: Optional[float] = None        # TMDB 평균 평점

    # 기획안 §2.4 분류 축
    is_polarizing: bool = False               # 호불호 뚜렷
    is_complex: bool = False                  # 서사 난해
    has_rich_tmi: bool = False                # TMI 풍부


class Review(BaseModel):
    """
    Watcha 리뷰. 임베딩과 해시태그는 별도 단계(Gemma 태깅)에서 채워짐.

    `tagger_version`은 모델 교체 시 추적용. 같은 리뷰가 다른 버전의 Gemma로
    재태깅될 수 있으므로 A/B 비교나 롤백 시 필수.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    movie_id: int                             # FK to Movie.id
    author: Optional[str] = None
    rating: Optional[float] = None            # 0.5 ~ 5.0 (Watcha 기준)
    text: str
    written_at: Optional[datetime] = None

    # 가공 결과 (Phase 3 이후 채워짐)
    sentiment: Optional[ReviewSentiment] = None
    hashtags: list[str] = Field(default_factory=list)
    tagger_version: Optional[str] = None      # 모델 교체 추적

    # 메타
    source_url: Optional[str] = None
    crawled_at: Optional[datetime] = None


class TMI(BaseModel):
    """TMI(촬영지·비하인드 등). DuckDuckGo 그라운딩 결과 정제본."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    movie_id: int
    category: TMICategory
    text: str
    source_url: Optional[str] = None
    confidence: Optional[float] = None        # 그라운딩 신뢰도 (옵션)
    grounded_at: Optional[datetime] = None


# ============================================================
# RAG 작업 단위 (그래프 안에서만 사용)
# ============================================================

class RetrievedDoc(BaseModel):
    """리트리버가 반환하는 단일 문서. QueryState.retrieved_docs의 요소."""
    text: str
    source: str                               # "review" | "tmi" | "tmdb" 등
    source_id: int                            # 원본 레코드 ID (출처 표시용)
    score: float                              # 유사도 점수 (0~1, 높을수록 관련)
    metadata: dict = Field(default_factory=dict)


class Citation(BaseModel):
    """답변에 포함되는 출처 인용. 기획안 §7 출처 제시율 90% 목표."""
    source: str                               # "review" | "tmi" | "tmdb"
    source_id: int
    snippet: str                              # 인용 텍스트 일부
    url: Optional[str] = None
