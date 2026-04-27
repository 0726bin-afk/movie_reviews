"""
basic_info 프롬프트 — 영화 기본 정보 답변용.

5종 질의 유형 중 첫 번째 (기획안 §3.3).
대상 질의 예: "기생충 감독이 누구야?", "미이라 줄거리 알려줘", "트루먼 쇼 출연진은?"

설계 원칙 (Phase 3에서 다른 4종 프롬프트 추가 시 동일 패턴):
- 검색된 자료를 근거로만 답하고 추측 금지
- 자료에 없는 내용은 "자료에 없음"이라고 명시
- 출처(영화 제목·감독·연도)를 답변 끝에 표시 — 기획안 §7 "출처 제시율 90%" 목표
"""
from langchain_core.prompts import ChatPromptTemplate

BASIC_INFO_TEMPLATE = """\
당신은 영화 도슨트입니다. 사용자의 질문에 친절하고 정확하게 답변하세요.
검색된 자료가 부족하면 모른다고 솔직히 말하세요. 절대 추측해서 답하지 마세요.

[사용자 질문]
{question}

[검색된 자료]
{context}

[답변 규칙]
1. 한국어로 답변
2. 검색된 자료에 있는 사실만 사용
3. 자료에 없는 내용은 "(자료에 없음)"이라고 명시
4. 답변 마지막에 출처를 한 줄로 표기 — 형식: `출처: <영화 제목> (<감독>, <연도>)`
5. 도슨트답게 우아하지만 군더더기 없이

답변:"""

basic_info_prompt = ChatPromptTemplate.from_template(BASIC_INFO_TEMPLATE)

__all__ = ["basic_info_prompt", "BASIC_INFO_TEMPLATE"]
