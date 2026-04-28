"""
RAG 그래프 — LangGraph StateGraph 조립.

Phase 4 토폴로지 (변화점은 ◆ 표시):

    START
      ↓
    cache_check   ◆ Phase 4 신설 — exact/similar 캐시 조회
      ↓
    [conditional]
      ├── cache_hit → END (즉시 반환)
      └── miss → route_query
                   ↓
                 retrieve
                   ↓
                 [conditional]
                   ├── tmi 류 + 자료 부족 → ground → generate
                   └── 그 외 → generate
                   ↓
                 save_cache  ◆ Phase 4 신설 — 답변을 캐시에 저장
                   ↓
                 END

Phase 4 추가:
  - cache_check / save_cache 노드 (이중 레이어 캐시)
  - checkpointer 적용 — session_id(thread_id)로 멀티턴 컨텍스트 유지
  - state.messages가 add_messages reducer로 자동 누적

Phase 3.5 잔여:
  - retrievers/self_query.py (현재 retrieve.py가 fake)
  - nodes/ground.py 본체 (현재 stub)
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from rag.nodes.cache_check import cache_check
from rag.nodes.generate import generate
from rag.nodes.ground import ground
from rag.nodes.retrieve import retrieve
from rag.nodes.route_query import route_query
from rag.nodes.save_cache import save_cache
from rag.state import QueryState


# ============================================================
# 조건부 분기 결정 함수
# ============================================================

def _after_cache_check(state: QueryState) -> str:
    """캐시 히트면 즉시 종료, 미스면 route_query로."""
    return "end" if state.get("cache_hit") else "continue"


def _post_retrieve_route(state: QueryState) -> str:
    """
    retrieve 노드 종료 후 ground을 거칠지 generate로 직행할지 결정.

    조건: tmi 류 질의이고 retrieve 결과가 빈약(tmi/review 자료 없음)할 때만 ground.
    반환값은 add_conditional_edges의 매핑 키와 일치해야 함.
    """
    qt = state.get("query_type")
    docs = state.get("retrieved_docs") or []
    tmi_docs = [d for d in docs if d.source in ("tmi", "review")]
    if qt == "tmi" and len(tmi_docs) == 0:
        return "ground"
    return "generate"


# ============================================================
# 그래프 빌드
# ============================================================

def build_graph(checkpointer=None, with_cache: bool = True):
    """
    LangGraph StateGraph 빌드 후 컴파일.

    Args:
        checkpointer: LangGraph BaseCheckpointSaver. None이면 기본(MemorySaver) 사용.
        with_cache: False면 cache_check/save_cache 노드를 끔 (디버깅·eval 시 캐시 우회).

    Returns:
        Compiled LangGraph runnable. invoke/ainvoke/stream 가능.
    """
    g = StateGraph(QueryState)

    # ---- 노드 등록 ----
    if with_cache:
        g.add_node("cache_check", cache_check)
        g.add_node("save_cache", save_cache)

    g.add_node("route_query", route_query)
    g.add_node("retrieve", retrieve)
    g.add_node("ground", ground)
    g.add_node("generate", generate)

    # ---- 엣지 ----
    if with_cache:
        # START → cache_check → (hit:END | miss:route_query)
        g.add_edge(START, "cache_check")
        g.add_conditional_edges(
            "cache_check",
            _after_cache_check,
            {"end": END, "continue": "route_query"},
        )
    else:
        g.add_edge(START, "route_query")

    # 메인 흐름
    g.add_edge("route_query", "retrieve")
    g.add_conditional_edges(
        "retrieve",
        _post_retrieve_route,
        {"ground": "ground", "generate": "generate"},
    )
    g.add_edge("ground", "generate")

    # generate 후 캐시 저장 → END (캐시 끄면 generate → END 직결)
    if with_cache:
        g.add_edge("generate", "save_cache")
        g.add_edge("save_cache", END)
    else:
        g.add_edge("generate", END)

    # ---- 컴파일 ----
    if checkpointer is None:
        from rag.checkpointer import get_default_checkpointer
        checkpointer = get_default_checkpointer()

    return g.compile(checkpointer=checkpointer)


# ============================================================
# 싱글턴 인스턴스 (지연 로딩)
# ============================================================

_compiled_graph = None


def get_graph():
    """그래프 싱글턴. 첫 호출 시 빌드."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def reset_graph() -> None:
    """테스트용. 빌드된 그래프 초기화."""
    global _compiled_graph
    _compiled_graph = None


# ============================================================
# CLI 진입점 — Phase 4 체크포인트 검증용
# ============================================================

def main() -> None:
    import sys

    from rag.state import empty_state

    question = (
        " ".join(sys.argv[1:]).strip()
        if len(sys.argv) > 1
        else "기생충 감독이 누구야?"
    )
    session_id = "default"

    print(f"\n[질문] {question}\n")

    graph = get_graph()

    # checkpointer 활성화 시 invoke에 thread_id config 필요
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(empty_state(question, session_id=session_id), config=config)

    print(f"[query_type]     {result.get('query_type')}")
    print(f"[target_movie]   {result.get('target_movie')}")
    print(f"[cache_hit]      {result.get('cache_hit')} ({result.get('cache_source')}, score={result.get('cache_score')})")
    print(f"[retrieved_docs] {len(result.get('retrieved_docs') or [])}건")
    print(f"[grounding_docs] {len(result.get('grounding_docs') or [])}건")
    print(f"[sources]        {len(result.get('sources') or [])}건")
    print(f"[latency_ms]     {result.get('latency_ms')}")
    print()
    print("[답변]")
    print(result.get("answer", "(no answer)"))
    print()


if __name__ == "__main__":
    main()
