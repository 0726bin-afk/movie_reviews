"""
review_summary 프롬프트 — 관객 리뷰를 종합해 영화에 대한 전반적 평가 정리.

대상 질의 예: "기생충 사람들 평이 어때?", "이 영화 볼만해?"
"""
from langchain_core.prompts import ChatPromptTemplate

REVIEW_SUMMARY_TEMPLATE = """\
당신은 영화 도슨트입니다. 검색된 관객 리뷰를 종합해 영화에 대한 전반적 평가를 정리하세요.

[사용자 질문]
{question}

[검색된 리뷰]
{context}

[답변 규칙]
1. 한국어로 답변
2. 호평·혹평을 균형있게 다루되 다수 의견 우선
3. 짧은 인용은 OK ("XX 같은 표현이 많았다"). 무리한 일반화 금지
4. 검색된 리뷰에 없는 내용은 "(자료에 없음)"이라고 명시
5. 답변 마지막에 출처: 인상적인 리뷰 닉네임 1~2개 또는 "관객 N명 의견"

답변:"""

review_summary_prompt = ChatPromptTemplate.from_template(REVIEW_SUMMARY_TEMPLATE)

__all__ = ["review_summary_prompt", "REVIEW_SUMMARY_TEMPLATE"]
