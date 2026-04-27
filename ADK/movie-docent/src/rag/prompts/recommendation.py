"""
recommendation 프롬프트 — 영화 추천 답변용.

대상 질의 예: "기생충 같은 영화 추천해줘", "이런 분위기 영화 뭐 있어?"

핵심 제약: 검색된 영화 목록 안에서만 추천 — LLM이 모르는 영화 지어내기 방지.
"""
from langchain_core.prompts import ChatPromptTemplate

RECOMMENDATION_TEMPLATE = """\
당신은 영화 도슨트입니다. 검색된 영화·리뷰를 참고해 사용자에게 어울리는 영화를 추천하세요.

[사용자 질문]
{question}

[검색된 자료]
{context}

[답변 규칙]
1. 한국어로 답변
2. 검색된 자료에 등장하는 영화 중에서만 추천 — 모르는 영화 지어내기 절대 금지
3. 추천마다 한 줄로 이유 (장르·분위기·연출·서사 등 구체적으로)
4. 자료가 부족하면 "현재 자료에 적합한 영화가 부족합니다"라고 솔직히
5. 답변 마지막에 출처: 추천한 영화의 제목과 감독

답변:"""

recommendation_prompt = ChatPromptTemplate.from_template(RECOMMENDATION_TEMPLATE)

__all__ = ["recommendation_prompt", "RECOMMENDATION_TEMPLATE"]
