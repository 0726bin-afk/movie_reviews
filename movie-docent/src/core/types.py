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

    movie_id: int                             # id -> movie_id
    title: str                                # 한국어 제목
    title_en: Optional[str] = None            # 추가: 영문 제목
    genre: Optional[str] = None               # genres(list) -> genre(str 쉼표 구분)
    director: Optional[str] = None
    release_date: Optional[date] = None
    tmdb_rating: Optional[float] = None       # rating_avg -> tmdb_rating
    tmdb_id: Optional[int] = None             # 추가
    kobis_id: Optional[str] = None            # 추가
    cast_members: Optional[str] = None        # cast(list) -> cast_members(str 쉼표 구분)
    overview: Optional[str] = None            # 줄거리
    poster_url: Optional[str] = None
    age_rating: Optional[str] = None          # 추가: 관람 등급

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
    review_id: int                            # id -> review_id
    movie_id: int                             # FK to Movie
    reviewer_nickname: Optional[str] = None   # author -> reviewer_nickname
    rating: Optional[float] = None            # 별점
    likes_count: int = 0                      # 추가: 좋아요 수
    comments_count: int = 0                   # 추가: 댓글 수
    content: str                              # text -> content
    sort_type: Optional[str] = None           # 추가: 수집 기준
    is_spoiler: bool = False                  # 추가: 스포일러 여부
    collected_at: Optional[datetime] = None   # written_at/crawled_at -> collected_at

    # 가공 결과 (Phase 3 이후 채워짐 - DB의 review_keywords 등으로 분리되나 객체엔 유지)
    sentiment: Optional[str] = None
    hashtags: list[str] = Field(default_factory=list)
    tagger_version: Optional[str] = None


class TMI(BaseModel):
    """TMI(촬영지·비하인드 등). DuckDuckGo 그라운딩 결과 정제본."""
    model_config = ConfigDict(from_attributes=True)

    tmi_id: int                               # id -> tmi_id
    movie_id: int
    category: str                             # TMICategory (문자열로 호환)
    content: str                              # text -> content
    source_url: Optional[str] = None
    created_at: Optional[datetime] = None     # grounded_at -> created_at

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
