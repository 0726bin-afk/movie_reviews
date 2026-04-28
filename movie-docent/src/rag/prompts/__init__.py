"""
프롬프트 레지스트리.

`get_prompt_for(query_type)`이 5종 프롬프트 중 하나를 반환.
generate 노드가 이 함수로 프롬프트를 받아 사용 — query_type 분기를 generate가 직접 가지지 않게.

사용 예:
    from rag.prompts import get_prompt_for
    prompt = get_prompt_for("basic_info")
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from rag.prompts.basic_info import basic_info_prompt
from rag.prompts.polarity import polarity_prompt
from rag.prompts.recommendation import recommendation_prompt
from rag.prompts.review_summary import review_summary_prompt
from rag.prompts.tmi import tmi_prompt


# query_type (state.QueryType과 1:1) → ChatPromptTemplate
PROMPT_REGISTRY: dict[str, ChatPromptTemplate] = {
    "basic_info": basic_info_prompt,
    "review_summary": review_summary_prompt,
    "tmi": tmi_prompt,
    "polarity": polarity_prompt,
    "recommendation": recommendation_prompt,
}


def get_prompt_for(query_type: str) -> ChatPromptTemplate:
    """query_type에 맞는 프롬프트 반환. 미존재 시 basic_info fallback."""
    return PROMPT_REGISTRY.get(query_type, basic_info_prompt)


__all__ = [
    "PROMPT_REGISTRY",
    "get_prompt_for",
    "basic_info_prompt",
    "review_summary_prompt",
    "tmi_prompt",
    "polarity_prompt",
    "recommendation_prompt",
]
