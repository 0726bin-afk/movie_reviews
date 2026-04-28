"""
챗봇 API — LangGraph astream 기반 SSE 스트리밍.

기존 CJB main.py의 단순 JSON 반환 /chat을 전면 교체:
  - 캐시 / RAG / 답변 생성 / 출처 분리 모두 LangGraph 그래프가 책임
  - 답변은 노드 단위로 SSE 이벤트로 흘려보냄
  - session_id로 멀티턴 컨텍스트 유지 (LangGraph Checkpointer)

이벤트 종류:
  - 'node':      노드 진입/종료 신호 (Streamlit 진행 표시용)
  - 'cache_hit': 캐시 히트 시 (즉시 종료 흐름임을 프론트에 알림)
  - 'token':     LLM 토큰 (현재는 emit 안 됨 — generate가 invoke 사용. Phase 5에서 astream 전환 시 자동 활성)
  - 'final':     최종 답변·출처 (generate 또는 cache_check 완료 시)
  - 'error':     예외 발생

Phase 5 enhancement:
  - generate.py가 llm.astream을 사용하도록 리팩토링 → 자동으로 token-level 스트리밍 작동
  - astream_events(version='v2') 'on_chat_model_stream'에서 토큰 흘러나옴
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from rag.graph import get_graph
from rag.state import empty_state

router = APIRouter(tags=["챗봇"])


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    movie_title: str | None = None  # CJB 기존 — target_movie 힌트로 사용


def _serialize_sources(sources: Any) -> list[dict]:
    """Citation Pydantic 객체를 dict로 직렬화."""
    if not sources:
        return []
    out = []
    for s in sources:
        if hasattr(s, "model_dump"):
            out.append(s.model_dump())
        elif isinstance(s, dict):
            out.append(s)
        else:
            out.append({"snippet": str(s)})
    return out


def _sse_data(payload: dict) -> str:
    """JSON 직렬화. 한글 그대로 보내고 ASCII escape 안 함."""
    return json.dumps(payload, ensure_ascii=False)


async def _stream_graph(req: ChatRequest) -> AsyncIterator[dict]:
    """
    LangGraph astream으로 노드 단위 스트리밍.
    각 yield는 sse_starlette EventSourceResponse가 받는 dict 형식.
    """
    session_id = req.session_id or "default"

    initial = empty_state(req.question, session_id=session_id)
    if req.movie_title:
        initial["target_movie"] = req.movie_title

    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    # 시작 신호 — 프론트가 placeholder 띄우기 좋게
    yield {
        "event": "node",
        "data": _sse_data({"node": "start", "session_id": session_id}),
    }

    final_state: dict = {}

    try:
        # mode="updates": 각 노드가 갱신한 부분 state만 보내옴
        async for chunk in graph.astream(initial, config=config, stream_mode="updates"):
            # chunk = {"node_name": partial_state}
            for node_name, partial in chunk.items():
                # 누적 추적 (final 이벤트용)
                final_state.update(partial or {})

                yield {
                    "event": "node",
                    "data": _sse_data({"node": node_name}),
                }

                # 캐시 히트 즉시 통지
                if node_name == "cache_check" and (partial or {}).get("cache_hit"):
                    yield {
                        "event": "cache_hit",
                        "data": _sse_data({
                            "source": partial.get("cache_source"),
                            "score": partial.get("cache_score"),
                        }),
                    }

        # 최종 답변
        yield {
            "event": "final",
            "data": _sse_data({
                "answer": final_state.get("answer", ""),
                "sources": _serialize_sources(final_state.get("sources")),
                "query_type": final_state.get("query_type"),
                "cache_hit": final_state.get("cache_hit", False),
                "session_id": session_id,
            }),
        }

    except Exception as e:
        yield {
            "event": "error",
            "data": _sse_data({"error": str(e), "type": type(e).__name__}),
        }


@router.post("/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    """
    SSE 스트리밍 엔드포인트.

    클라이언트는 EventSource 또는 requests.iter_lines로 SSE 이벤트를 받음.
    각 이벤트는 'event: <name>\\ndata: <json>\\n\\n' 형식.
    """
    return EventSourceResponse(_stream_graph(req))
