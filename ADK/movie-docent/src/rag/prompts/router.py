"""
router 프롬프트 — 사용자 질문을 5종 query_type 중 하나로 분류.

기획안 §3.3 5종 (state.QueryType과 정확히 일치):
  - basic_info     : 영화 기본 정보
  - review_summary : 리뷰 요약
  - tmi            : 비하인드·촬영지·OST·옥에티·캐스팅비화
  - polarity       : 호불호 분석
  - recommendation : 추천

설계 메모:
- few-shot 예시 7개로 분류 정확도 끌어올림
- 출력은 카테고리명 한 단어만 — `route_query` 노드가 substring matching으로 파싱
- 분류 실패 시 fallback은 basic_info (가장 안전)
"""
from langchain_core.prompts import ChatPromptTemplate

ROUTER_TEMPLATE = """\
사용자의 영화 관련 질문을 다음 5개 카테고리 중 정확히 하나로 분류하세요.

[카테고리]
- basic_info: 영화 기본 정보 (감독·줄거리·캐스팅·개봉일·평점·러닝타임 등)
- review_summary: 관객 리뷰 요약 (전반적 평가·반응·볼만한지)
- tmi: 비하인드·촬영지·OST·옥에티·캐스팅비화 등 부가정보
- polarity: 호불호 갈리는 이유, 호평·혹평 대조
- recommendation: 영화 추천 요청 (비슷한 영화·이런 분위기 등)

[예시]
질문: 기생충 감독이 누구야?
분류: basic_info

질문: 기생충 사람들 평이 어때?
분류: review_summary

질문: 기생충 촬영지 어디야?
분류: tmi

질문: 기생충은 왜 호불호가 갈려?
분류: polarity

질문: 기생충 같은 영화 추천해줘
분류: recommendation

질문: 트루먼 쇼 어디서 찍었어?
분류: tmi

질문: 이 영화 볼만해?
분류: review_summary

[규칙]
- 위 5개 중 정확히 하나만 출력
- 카테고리명 외 다른 단어 출력 금지

[질문]
{question}

분류:"""

router_prompt = ChatPromptTemplate.from_template(ROUTER_TEMPLATE)

__all__ = ["router_prompt", "ROUTER_TEMPLATE"]
