"""
router 프롬프트 — 사용자 질문을 5종 query_type 분류 및 영화 제목 추출.

기획안 §3.3 5종 및 target_movie 추출:
  - basic_info     : 영화 기본 정보
  - review_summary : 리뷰 요약
  - tmi            : 비하인드·촬영지·OST·옥에티·캐스팅비화
  - polarity       : 호불호 분석
  - recommendation : 추천
"""
from langchain_core.prompts import ChatPromptTemplate

ROUTER_TEMPLATE = """\
사용자의 영화 관련 질문을 분석하여 아래 형식에 맞춰 카테고리와 영화 제목을 추출하세요.

[카테고리 목록]
- basic_info: 영화 기본 정보 (감독·줄거리·캐스팅·개봉일·평점 등)
- review_summary: 관객 리뷰 요약 및 전반적 평판
- tmi: 비하인드·촬영지·OST·옥에티·캐스팅비화 등
- polarity: 호불호 갈리는 이유, 호평·혹평 대조
- recommendation: 영화 추천 요청

[규칙]
1. query_type: 위 5개 중 가장 적합한 하나를 선택하세요.
2. target_movie: 질문에서 언급된 영화 제목을 추출하세요. 제목이 명확하지 않거나 추천 요청처럼 대상이 없으면 'None'이라고 적으세요.
3. 출력 형식: 아래 예시와 같이 두 줄로 출력하세요. 다른 설명은 생략하세요.

[예시]
질문: 기생충 감독이 누구야?
출력:
query_type: basic_info
target_movie: 기생충

질문: 요즘 볼만한 영화 추천해줄래?
출력:
query_type: recommendation
target_movie: None

질문: <인셉션> 비하인드 스토리 알려줘
출력:
query_type: tmi
target_movie: 인셉션

질문: 사람들이 이 영화 볼만하대?
출력:
query_type: review_summary
target_movie: None

[질문]
{question}

출력:"""

router_prompt = ChatPromptTemplate.from_template(ROUTER_TEMPLATE)

__all__ = ["router_prompt", "ROUTER_TEMPLATE"]
