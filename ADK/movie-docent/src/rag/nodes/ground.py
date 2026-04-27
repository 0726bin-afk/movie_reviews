"""
ground 노드 — 실시간 그라운딩 (DuckDuckGo).

흐름 설계 (사용자 합의):
  1. retrieve가 먼저 DB(또는 fixture)에서 자료 검색
  2. tmi 류 질문에서 결과 부족하면 그래프가 이 노드로 라우팅
  3. 여기서 DuckDuckGo로 카테고리별 검색
  4. 결과 정제 → movie_tmi 테이블에 INSERT (Phase 4 DB 연동 시)
  5. RetrievedDoc 리스트로 state.grounding_docs 채움 → generate가 사용

Phase 3 현재: stub.
- DuckDuckGo 호출 없이 빈 grounding_docs 반환
- 그래프 토폴로지·state 인터페이스를 미리 박아둠
- Phase 3.5에서 실제 검색·DB 적재 로직 채움
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.types import RetrievedDoc
    from rag.state import QueryState


# 기획안 §3.2 TMI 카테고리 (CJB schema와 통일)
TMI_CATEGORIES = ["촬영지", "OST", "비하인드", "옥에티", "캐스팅비화"]


def ground(state: "QueryState") -> "QueryState":
    """
    그라운딩 진입 = retrieve 결과가 부족하다는 판단이 이미 났다는 뜻.

    Phase 3.5에서 채울 작업:
      - DDGS()로 카테고리별 검색
      - 결과 텍스트·URL을 RetrievedDoc으로 래핑
      - movie_tmi 테이블에 INSERT (CJB의 적재 로직 참고)
    """
    t0 = time.perf_counter()

    question = state.get("question", "")
    target = state.get("target_movie")

    # TODO(phase-3.5): 실제 그라운딩
    # from duckduckgo_search import DDGS
    # results = []
    # with DDGS() as ddgs:
    #     for category in TMI_CATEGORIES:
    #         query = f"{target or ''} 영화 {category}".strip()
    #         results.extend(ddgs.text(query, region="kr-kr", max_results=2))
    # grounding_docs = [
    #     RetrievedDoc(text=r["body"], source="grounded", source_id=i,
    #                  score=0.6, metadata={"url": r["href"], "category": ...})
    #     for i, r in enumerate(results)
    # ]
    # # DB 적재는 별도 db.repositories.tmi_repo.insert_many 호출
    grounding_docs: list = []

    latency = (time.perf_counter() - t0) * 1000
    return {
        **state,
        "grounding_docs": grounding_docs,
        "needs_grounding": False,  # 처리 완료
        "latency_ms": {**(state.get("latency_ms") or {}), "ground": latency},
    }
