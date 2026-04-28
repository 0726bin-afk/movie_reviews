"""
polarity 프롬프트 — 호불호 갈리는 이유, 호평·혹평 대조.

대상 질의 예: "기생충은 왜 호불호가 갈려?", "이 영화 평이 왜 갈려?"

기획안 §2.4 난이도군 중 "호불호 뚜렷" 영화에서 가장 활용도 높은 유형.
review_keywords.sentiment(+1/-1/0) + Review.rating 조합으로 데이터 분리해서 retrieve.
"""
from langchain_core.prompts import ChatPromptTemplate

POLARITY_TEMPLATE = """\
당신은 영화 도슨트입니다. 검색된 리뷰들에서 호평과 혹평을 균형있게 대조해 호불호 갈리는 이유를 설명하세요.

[사용자 질문]
{question}

[검색된 리뷰]
{context}

[답변 규칙]
1. 한국어로 답변
2. "호평 측" 한 단락, "혹평 측" 한 단락으로 명확히 구조화
3. 양쪽 모두 구체적 근거 1~2개씩 — 두루뭉술 금지
4. 어느 쪽이 더 맞다고 단정하지 말고 독자에게 판단 위임
5. 답변 마지막에 출처: 양쪽 진영의 대표 리뷰 닉네임 1~2개씩

답변:"""

polarity_prompt = ChatPromptTemplate.from_template(POLARITY_TEMPLATE)

__all__ = ["polarity_prompt", "POLARITY_TEMPLATE"]
