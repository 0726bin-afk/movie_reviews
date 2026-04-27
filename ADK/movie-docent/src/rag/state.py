"""
RAG 그래프의 전역 State.

LangGraph의 모든 노드는 시그니처가 (state) -> state 형태.
이 TypedDict가 모든 노드 간의 계약(contract)이다.

설계 원칙:
- `total=False`이므로 모든 필드는 선택적
- 각 노드는 자기가 책임지는 필드만 채우거나 갱신
- 새 필드 추가 시 모든 노드가 영향받으므로 신중하게

`messages` 필드는 Phase 4에서 Annotated[..., add_messages] reducer로 업그레이드 예정.
지금은 plain list로 단순하게.
"""
from typing import Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage

from core.types import Citation, RetrievedDoc


# ============================================================
# 5종 질의 유형 (기획안 §3.3)
# ============================================================
QueryType = Literal[
    "basic_info",       # 영화 기본 정보 (감독·줄거리·캐스팅)
    "review_summary",   # 리뷰 요약
    "tmi",              # 비하인드·촬영지·OST·옥에 티
    "polarity",         # 호불호 분석 (상반 리뷰 대조)
    "recommendation",   # 추천
]

# 캐시 매칭 종류 (기획안 §4.1 이중 레이어)
CacheSource = Literal["exact", "similar"]


# ============================================================
# QueryState
# ============================================================

class QueryState(TypedDict, total=False):
    """그래프 상태 — 노드 간 계약."""

    # ====== 입력 ======
    question: str                        # 사용자 질문
    session_id: str                      # 멀티턴 식별자 (Checkpointer key)
    messages: list[BaseMessage]          # 멀티턴 히스토리 (Phase 4)

    # ====== 라우팅 (route_query 노드가 채움) ======
    query_type: Optional[QueryType]
    target_movie: Optional[str]          # 추출된 영화명 (있으면 검색 필터로 사용)

    # ====== 캐시 (cache_check 노드가 채움) ======
    cache_hit: bool
    cache_source: Optional[CacheSource]  # "exact" | "similar"
    cache_score: Optional[float]         # 유사 매칭 시 코사인 점수

    # ====== 검색 (retrieve / ground 노드가 채움) ======
    retrieved_docs: list[RetrievedDoc]   # Self-Query Retriever 결과
    grounding_docs: list[RetrievedDoc]   # DuckDuckGo 그라운딩 결과 (필요 시)
    needs_grounding: bool                # ground 노드 진입 여부 (라우팅 결정)

    # ====== 생성 (generate 노드가 채움) ======
    answer: str                          # 최종 답변 텍스트
    sources: list[Citation]              # 출처 인용 (기획안 §7 출처 제시율 90% 목표)

    # ====== 관측 (모든 노드가 부분 갱신) ======
    trace_id: str                        # LangSmith 트레이싱용
    latency_ms: dict[str, float]         # node_name -> ms
    error: Optional[str]                 # 노드 실행 중 에러 메시지 (있으면)


# ============================================================
# Helpers
# ============================================================

def empty_state(question: str, session_id: str = "default") -> QueryState:
    """
    초기 state 생성. 그래프 invoke 전 필수 필드를 기본값으로 채움.

    사용 예:
        state = empty_state("기생충 줄거리 알려줘")
        result = graph.invoke(state)
    """
    return QueryState(
        question=question,
        session_id=session_id,
        messages=[],
        cache_hit=False,
        retrieved_docs=[],
        grounding_docs=[],
        needs_grounding=False,
        sources=[],
        latency_ms={},
    )
