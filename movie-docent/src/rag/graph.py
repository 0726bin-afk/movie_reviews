"""
RAG 그래프 — LangGraph StateGraph 조립.

토폴로지:
    START
      v
    cache_check
      v
    [conditional]
      cache_hit -> END
      miss -> route_query -> retrieve -> [tmi+빈 자료? -> ground] -> generate -> save_cache -> END

Phase 5: 모든 노드 async. CLI는 asyncio.run(graph.ainvoke).
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


def _after_cache_check(state: QueryState) -> str:
    """캐시 히트면 즉시 종료, 미스면 route_query로."""
    return "end" if state.get("cache_hit") else "continue"


def _post_retrieve_route(state: QueryState) -> str:
    """tmi 류 + retrieve 결과 빈약하면 ground 거쳐 보강."""
    qt = state.get("query_type")
    docs = state.get("retrieved_docs") or []
    tmi_docs = [d for d in docs if d.source in ("tmi", "review")]
    if qt == "tmi" and len(tmi_docs) == 0:
        return "ground"
    return "generate"


def build_graph(checkpointer=None, with_cache: bool = True):
    """LangGraph StateGraph 빌드 후 컴파일."""
    g = StateGraph(QueryState)

    if with_cache:
        g.add_node("cache_check", cache_check)
        g.add_node("save_cache", save_cache)

    g.add_node("route_query", route_query)
    g.add_node("retrieve", retrieve)
    g.add_node("ground", ground)
    g.add_node("generate", generate)

    if with_cache:
        g.add_edge(START, "cache_check")
        g.add_conditional_edges(
            "cache_check",
            _after_cache_check,
            {"end": END, "continue": "route_query"},
        )
    else:
        g.add_edge(START, "route_query")

    g.add_edge("route_query", "retrieve")
    g.add_conditional_edges(
        "retrieve",
        _post_retrieve_route,
        {"ground": "ground", "generate": "generate"},
    )
    g.add_edge("ground", "generate")

    if with_cache:
        g.add_edge("generate", "save_cache")
        g.add_edge("save_cache", END)
    else:
        g.add_edge("generate", END)

    if checkpointer is None:
        from rag.checkpointer import get_default_checkpointer
        checkpointer = get_default_checkpointer()

    return g.compile(checkpointer=checkpointer)


_compiled_graph = None


def get_graph():
    """그래프 싱글턴. 첫 호출 시 빌드."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def reset_graph() -> None:
    """테스트용."""
    global _compiled_graph
    _compiled_graph = None


async def _amain(question: str, session_id: str = "default") -> None:
    """async 진입 — 모든 노드가 async라 ainvoke로 호출."""
    from rag.state import empty_state

    print("=" * 55)
    print(f"  질문: {question}")
    print("=" * 55)

    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}
    result = await graph.ainvoke(
        empty_state(question, session_id=session_id),
        config=config,
    )

    # ── 노드별 소요시간 요약 ──────────────────────────────
    latency: dict = result.get("latency_ms") or {}
    NODE_ORDER = ["cache_check", "route_query", "retrieve", "ground", "generate", "save_cache"]
    total_ms = sum(latency.values())

    print("\n" + "─" * 55)
    print("  ⏱  노드별 소요시간")
    print("─" * 55)
    for node in NODE_ORDER:
        if node in latency:
            ms = latency[node]
            bar = "█" * max(1, int(ms / 100))   # 100ms = ▊ 1칸
            print(f"  {node:<14} {ms:>7.0f} ms  {bar}")
    print("─" * 55)
    print(f"  {'합계':<14} {total_ms:>7.0f} ms")
    print("─" * 55)

    # ── 결과 요약 ─────────────────────────────────────────
    cache_hit = result.get("cache_hit")
    cache_src = result.get("cache_source")
    print(f"\n  유형:   {result.get('query_type')}  |  영화: {result.get('target_movie')}")
    if cache_hit:
        print(f"  캐시:   히트 ({cache_src})  → 노드 건너뜀")
    else:
        print(f"  캐시:   미스")
    print(f"  문서:   retrieved {len(result.get('retrieved_docs') or [])}건  "
          f"/ grounding {len(result.get('grounding_docs') or [])}건  "
          f"/ 출처 {len(result.get('sources') or [])}건")

    print("\n" + "─" * 55)
    print("  답변")
    print("─" * 55)
    print(result.get("answer", "(no answer)"))
    print("=" * 55 + "\n")


def main() -> None:
    """동기 CLI — asyncio.run으로 _amain 실행."""
    import asyncio
    import sys

    from db.client import close_pool

    question = (
        " ".join(sys.argv[1:]).strip()
        if len(sys.argv) > 1
        else "기생충 감독이 누구야?"
    )

    async def _runner():
        try:
            await _amain(question)
        finally:
            await close_pool()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()
