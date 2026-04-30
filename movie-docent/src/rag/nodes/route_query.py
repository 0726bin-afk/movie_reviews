"""
route_query 노드 — 질문을 5종 query_type 중 하나로 분류.

state -> state.
입력: question
출력: query_type, target_movie

설계:
- LLM 출력에서 카테고리 단어를 substring으로 매칭
- 미매칭 시 'basic_info' fallback
- target_movie는 따옴표/꺾쇠 휴리스틱
- Phase 5: async — llm.ainvoke 사용
"""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from providers.llm import get_llm
from rag.prompts.router import router_prompt

if TYPE_CHECKING:
    from rag.state import QueryState


VALID_QUERY_TYPES = (
    "basic_info",
    "review_summary",
    "tmi",
    "polarity",
    "recommendation",
)


def _extract_target_movie(question: str) -> str | None:
    """따옴표·꺾쇠 안 텍스트가 있으면 영화 제목으로 간주."""
    for pat in [r'"([^"]+)"', r'「([^」]+)」', r'《([^》]+)》', r'<([^>]+)>']:
        m = re.search(pat, question)
        if m:
            return m.group(1).strip()
    return None

def _parse_query_type(raw: str) -> str:
    """LLM 출력에서 카테고리명 substring matching."""
    text = raw.strip().lower()
    for cat in VALID_QUERY_TYPES:
        if cat in text:
            return cat
    return "basic_info"

def _parse_llm_response(raw: str):
    """LLM의 출력에서 유형과 제목을 동시에 추출"""
    text = raw.strip().lower()
    
    # 1. query_type 찾기
    selected_type = "basic_info" # 기본값
    for cat in VALID_QUERY_TYPES:
        if cat in text:
            selected_type = cat
            break
            
    # 2. target_movie 찾기 (정규표현식으로 target_movie: 뒷부분 추출)
    target_movie = None
    match = re.search(r"target_movie:\s*(.+)", raw, re.IGNORECASE)
    if match:
        val = match.group(1).strip()
        if val.lower() != "none":
            target_movie = val
            
    return selected_type, target_movie


async def route_query(state: "QueryState") -> "QueryState":
    t0 = time.perf_counter()
    question = state.get("question", "")
    llm = get_llm()

    prompt_value = router_prompt.format_prompt(question=question)
    raw = await llm.ainvoke(prompt_value.to_string())
    
    # 수정된 파싱 함수 사용
    query_type, target_movie = _parse_llm_response(raw)

   # LLM이 제목을 못 찾았을 때만 기존의 따옴표 로직으로 보완
    if not target_movie:
        target_movie = _extract_target_movie(question)

    return {
        **state,
        "query_type": query_type,
        "target_movie": target_movie, # 이제 드디어 '기생충'이 담깁니다!
        # ... 
    }
