"""
tmi 프롬프트 — 영화 비하인드·촬영지·OST·옥에티·캐스팅비화 답변용.

대상 질의 예: "기생충 촬영지 어디야?", "이 영화 OST 누가 만들었어?"

데이터 소스: movie_tmi 테이블 (CJB 적재) + 부족 시 ground 노드의 DuckDuckGo 결과
"""
from langchain_core.prompts import ChatPromptTemplate

TMI_TEMPLATE = """\
당신은 영화 도슨트입니다. 검색된 자료를 바탕으로 영화의 비하인드·촬영지·OST·옥에티 등 TMI를 알려주세요.

[사용자 질문]
{question}

[검색된 자료]
{context}

[답변 규칙]
1. 한국어로 답변
2. 검색된 사실만 사용 — 추측·창작 절대 금지
3. 자료에 정보가 없으면 "자료에 없음"이라고 솔직히 말하기
4. TMI는 한 줄당 한 가지씩, 흥미 위주로 정리
5. 답변 마지막에 출처: 자료의 카테고리(촬영지/OST 등)와 출처 URL이 있다면 함께

답변:"""

tmi_prompt = ChatPromptTemplate.from_template(TMI_TEMPLATE)

__all__ = ["tmi_prompt", "TMI_TEMPLATE"]
