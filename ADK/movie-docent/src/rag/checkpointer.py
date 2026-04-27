"""
LangGraph Checkpointer 팩토리.

Checkpointer는 그래프 실행 상태를 저장해서 멀티턴 대화에서 컨텍스트를 유지.
session_id(thread_id)를 키로 state 스냅샷을 보관 → 다음 호출 시 복원.

Phase 4 현재:
- 기본: `MemorySaver` (in-process)
- 옵션: `PostgresSaver` (settings.SUPABASE_DB_URL이 설정되고 APP_ENV != "dev"일 때)

Phase 5/배포 시점:
- 무조건 `PostgresSaver`로 — 재시작 후 대화 이어가기 가능.
- DB에 `checkpoints` 테이블 자동 생성됨 (LangGraph 내부 스키마).

사용 예:
    from rag.checkpointer import get_checkpointer
    checkpointer = get_checkpointer()
    graph = build_graph(checkpointer=checkpointer)
"""
from __future__ import annotations

from config.settings import settings


def get_checkpointer():
    """
    settings에 따라 Checkpointer 구현체를 라우팅.

    반환 타입은 LangGraph BaseCheckpointSaver의 인스턴스 (또는 컨텍스트 매니저).
    """
    use_postgres = (
        settings.APP_ENV in ("staging", "prod")
        and bool(settings.SUPABASE_DB_URL)
    )

    if use_postgres:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as e:
            raise ImportError(
                "Postgres checkpointer 사용하려면 `pip install langgraph-checkpoint-postgres` "
                "또는 `pip install -e .` (pyproject 의존성에 이미 포함)."
            ) from e
        # PostgresSaver는 컨텍스트 매니저 형태로도 쓸 수 있음.
        # 여기서는 단순 from_conn_string. 첫 호출 시 setup() 한 번 필요할 수 있음 (LangGraph 버전마다 다름).
        return PostgresSaver.from_conn_string(settings.SUPABASE_DB_URL)

    # 기본: in-memory
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


# ============================================================
# 싱글턴 (한 프로세스에 하나)
# ============================================================

_checkpointer = None


def get_default_checkpointer():
    """프로세스 전역 싱글턴. 그래프 빌드 시 사용."""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = get_checkpointer()
    return _checkpointer


def reset_checkpointer() -> None:
    """테스트용."""
    global _checkpointer
    _checkpointer = None


__all__ = ["get_checkpointer", "get_default_checkpointer", "reset_checkpointer"]
