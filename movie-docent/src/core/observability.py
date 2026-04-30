"""
LangSmith 트레이싱 초기화.

왜 이 파일이 필요한가?
  settings.py는 우리 프로젝트 규칙대로 LANGSMITH_* 이름을 쓰지만,
  LangChain/LangGraph가 실제로 읽는 환경변수는 LANGCHAIN_* 이름이다.
  이 모듈이 둘을 연결해준다.

사용법:
  build_graph(), FastAPI lifespan 등 앱 시작 시점에 딱 한 번 호출.
    from core.observability import configure_langsmith
    configure_langsmith()

트레이싱 ON/OFF:
  .env 의 LANGSMITH_TRACING=true/false 만 바꾸면 됨. 코드 수정 불필요.
"""
from __future__ import annotations

import os


def configure_langsmith() -> bool:
    """
    LANGSMITH_* 설정을 LangChain 표준 환경변수로 변환하여 트레이싱을 활성화한다.

    Returns:
        True  — 트레이싱 활성화 성공
        False — 비활성(LANGSMITH_TRACING=false) 또는 API 키 없음
    """
    # settings를 여기서 import해야 순환 import 없이 안전
    from config.settings import settings

    if not settings.LANGSMITH_TRACING:
        return False

    if not settings.LANGSMITH_API_KEY:
        print(
            "⚠️  [LangSmith] LANGSMITH_TRACING=true 이지만 "
            "LANGSMITH_API_KEY가 비어 있습니다.\n"
            "   .env 에 키를 입력하거나 LANGSMITH_TRACING=false 로 되돌리세요."
        )
        return False

    # LangChain/LangGraph가 읽는 표준 이름으로 매핑
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"]     = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"]     = settings.LANGSMITH_PROJECT

    print(
        f"✅ [LangSmith] 트레이싱 활성화 "
        f"(project: {settings.LANGSMITH_PROJECT})\n"
        f"   대시보드 → https://smith.langchain.com/"
    )
    return True
