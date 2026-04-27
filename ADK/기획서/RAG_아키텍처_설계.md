# RAG 아키텍처 설계안

> **참조 기획안**: `프로젝트 기획안 (Project Proposal)1.2.md` (v1.2, 2026-04-23)
> **전제**: LangGraph(오케스트레이션) + LangChain(컴포넌트) 혼합, Supabase(PostgreSQL + pgvector) 단일화
> **설계 우선순위**: ① 모델 교체 용이성 (LLM/Embedding/Tagger) ② 노드 단위 디버깅 용이성 ③ 오프라인/온라인 분리

---

## 1. 기능 정의 — 7개 레이어

| # | 레이어 | 역할 | 실행 주기 |
| --- | --- | --- | --- |
| ① | **Ingestion (데이터 수집)** | TMDB API, Watcha Playwright 크롤러, DuckDuckGo 초기 TMI | 오프라인 (배치) |
| ② | **Tagging** | Gemma 기반 리뷰 해시태그(#연기호평 등) JSON 산출 | 오프라인 (배치) |
| ③ | **Embedding & Load** | Gemini 임베딩 → Supabase pgvector HNSW 적재 | 오프라인 (배치) |
| ④ | **RAG Graph (질의응답)** | LangGraph State Machine: cache_check → route_query → retrieve → (조건부) ground → generate → save_cache | 온라인 (요청 단위) |
| ⑤ | **Providers (모델 추상화)** | LLM/Embedding/Tagger 팩토리. `.env`로 교체 | 공통 |
| ⑥ | **API Layer** | FastAPI `/chat` 스트리밍, 세션 관리, LangGraph Checkpointer (Supabase) | 온라인 |
| ⑦ | **Evaluation & Observability** | eval_set, query_log, 메트릭 (MVP 성공 기준 검증) | 주기적 |

기획안 §3.3 **질의 유형 5종** (기본정보 / 리뷰 요약 / TMI / 호불호 / 추천)은 ④의 `route_query` 노드에서 분기되고, 각 분기는 `rag/prompts/` 아래 독립 파일로 분리되어 유형별 개선이 쉬움.

---

## 2. 설계 원칙 3가지

### 원칙 1. 노드 = 파일, 시그니처 = `(state) -> state` 순수 함수
LangGraph 노드를 하나씩 독립 파일로 분리. pytest에서 state 딕셔너리 하나 넣어 단독 호출 가능. 그래프 전체를 돌리지 않고도 노드 하나의 회귀를 잡을 수 있음.

### 원칙 2. 외부 모델 SDK는 `providers/` 안에서만 import
노드 코드 어디에서도 `google.generativeai`, `openai` 같은 패키지를 직접 import하지 않음. 전부 `from providers.llm import get_llm`. 덕분에 모델 교체 = `.env` 한 줄.

### 원칙 3. Ingestion(오프라인)과 RAG(온라인) 완전 분리
실행 주기·실패 모드·의존성이 완전히 다름. 섞으면 크롤러 실패가 런타임 서버로 번짐.

---

## 3. 파일 구조

```
movie-docent/
├── README.md
├── pyproject.toml
├── .env.example                 # 모든 모델 선택 플래그가 여기로
│
├── config/
│   ├── settings.py              # Pydantic BaseSettings — env 로드
│   └── model_registry.py        # provider별 기본 파라미터 매핑
│
├── src/
│   ├── core/                    # 공통 타입·예외·로깅
│   │   ├── types.py             # Movie, Review, TMI, QueryState 등 Pydantic
│   │   ├── exceptions.py
│   │   └── logging.py
│   │
│   ├── providers/               # ⭐ 모델 교체 용이성의 심장
│   │   ├── base.py              # LLMProvider, EmbeddingProvider, TaggerProvider ABC
│   │   ├── llm/
│   │   │   ├── __init__.py      # get_llm(name=None) 팩토리
│   │   │   ├── gemini.py
│   │   │   ├── openai.py
│   │   │   └── claude.py
│   │   ├── embedding/
│   │   │   ├── __init__.py      # get_embedder(name=None) 팩토리
│   │   │   ├── gemini.py
│   │   │   └── openai.py
│   │   └── tagger/
│   │       ├── __init__.py      # get_tagger(name=None) 팩토리
│   │       ├── gemma_local.py   # Ollama / llama.cpp 로컬 실행
│   │       └── hf_endpoint.py
│   │
│   ├── db/                      # Supabase + pgvector
│   │   ├── client.py            # asyncpg / supabase-py 싱글턴
│   │   ├── schema.sql           # movies / reviews / tmi / qa_cache / query_log DDL
│   │   ├── migrations/          # 재임베딩용 컬럼 스왑 스크립트 포함
│   │   └── repositories/        # ⭐ 모든 SQL은 여기서만
│   │       ├── movies_repo.py
│   │       ├── reviews_repo.py
│   │       ├── tmi_repo.py
│   │       ├── cache_repo.py    # hash 정확매칭 + embedding 유사매칭 이중 레이어
│   │       └── log_repo.py
│   │
│   ├── ingestion/               # ⭐ 오프라인 파이프라인
│   │   ├── crawlers/
│   │   │   ├── tmdb_client.py
│   │   │   ├── watcha_playwright.py
│   │   │   └── duckduckgo_client.py
│   │   ├── tagging/
│   │   │   ├── prompts.py       # Gemma 태깅 프롬프트 + 허용 해시태그 화이트리스트
│   │   │   └── pipeline.py      # 배치 태깅 러너
│   │   ├── embedding/
│   │   │   └── pipeline.py      # 청크 → 임베딩 → upsert
│   │   └── run.py               # CLI: python -m ingestion.run --stage crawl|tag|embed
│   │
│   ├── rag/                     # ⭐ LangGraph + LangChain 런타임
│   │   ├── state.py             # QueryState (TypedDict) — 그래프 전체 state 스키마
│   │   ├── graph.py             # StateGraph 조립. 이 파일만 보면 전체 흐름 파악 가능
│   │   ├── checkpointer.py      # Supabase Postgres Checkpointer (멀티턴)
│   │   │
│   │   ├── nodes/               # ⭐ 1-노드-1-파일
│   │   │   ├── cache_check.py
│   │   │   ├── route_query.py   # 5종 분류
│   │   │   ├── retrieve.py      # Self-Query Retriever 호출
│   │   │   ├── ground.py        # DuckDuckGo (조건부)
│   │   │   ├── generate.py
│   │   │   └── save_cache.py
│   │   │
│   │   ├── retrievers/          # LangChain 컴포넌트
│   │   │   ├── self_query.py    # pgvector + 메타데이터 필터
│   │   │   └── hybrid.py        # 필요 시 keyword+vector 하이브리드
│   │   │
│   │   ├── prompts/             # 질의 유형별 — 수정이 가장 잦은 곳
│   │   │   ├── router.py
│   │   │   ├── basic_info.py
│   │   │   ├── review_summary.py
│   │   │   ├── tmi.py
│   │   │   ├── polarity.py      # 호불호
│   │   │   └── recommendation.py
│   │   │
│   │   └── parsers/
│   │       └── answer_parser.py
│   │
│   ├── api/                     # FastAPI
│   │   ├── main.py
│   │   ├── schemas.py           # Request/Response
│   │   ├── routes/
│   │   │   ├── chat.py          # POST /chat (SSE 스트리밍)
│   │   │   └── health.py
│   │   └── dependencies.py      # graph 싱글턴 주입
│   │
│   └── eval/
│       ├── eval_set.yaml        # 50문항 수동 평가셋
│       ├── metrics.py
│       └── run_eval.py
│
├── frontend/
│   └── app.py                   # MVP Streamlit
│
├── tests/
│   ├── unit/                    # 노드·리포지토리·파서 단위 테스트
│   ├── integration/             # 그래프 end-to-end (fake LLM 주입)
│   └── fixtures/
│       └── sample_state.json
│
├── scripts/
│   ├── setup_db.py              # schema.sql 실행
│   ├── benchmark_retriever.py   # HNSW 파라미터 튜닝
│   └── reembed.py               # 임베딩 모델 교체 시 재임베딩 절차
│
├── data/                        # (.gitignore)
└── notebooks/                   # 프로토타이핑
```

---

## 4. 모델 교체 — 실제 작업 흐름

### 4.1. LLM 교체 (Gemini ↔ GPT-4o ↔ Claude)
1. `.env` 수정 — `LLM_PROVIDER=openai`
2. 서버 재시작. 끝.

노드 코드는 손대지 않음. `generate.py` 내부는 다음과 같이 provider 중립:

```python
# src/rag/nodes/generate.py
from providers.llm import get_llm
from rag.prompts import basic_info, review_summary  # 등

def generate(state: QueryState) -> QueryState:
    llm = get_llm()                           # ← .env만 보고 교체됨
    prompt = _select_prompt(state["query_type"])
    state["answer"] = llm.invoke(prompt.format(**state))
    state["sources"] = _extract_sources(state)
    return state
```

### 4.2. Embedding 교체
임베딩은 **저장된 벡터를 재계산**해야 하므로 절차가 있음. 기획안 §4.1의 무중단 스왑을 `scripts/reembed.py`로 자동화:

1. 새 컬럼 `embedding_v2` 추가 (HNSW 인덱스 별도).
2. 배치 작업으로 모든 레코드 재임베딩하여 `embedding_v2` 채움.
3. 트랜잭션 내에서 `embedding` ↔ `embedding_v2` 스왑.
4. 구 컬럼 드롭.

> **권장**: 기획안 §8 리스크의 "1주차 임베딩 후보 2~3종 비교"가 이 스크립트 없이 불가능하므로, `reembed.py`를 **1주차에 먼저** 작성.

### 4.3. Tagger 교체 (Gemma ↔ 다른 OSS)
오프라인에만 영향. 대신 해시태그 스키마가 달라질 수 있으므로:
- `ingestion/tagging/prompts.py`에 **허용 해시태그 화이트리스트**를 상수로 고정.
- 리뷰 레코드에 `tagger_version` 필드 추가 → A/B 비교·롤백 가능.
- Self-Query Retriever가 참조하는 메타데이터 필드 집합과 화이트리스트를 **동일 상수 모듈에서 import**하도록 강제.

---

## 5. QueryState 스키마 (그래프 전체 계약)

노드 간 계약이므로 **처음 결정이 가장 중요**. 최소 필드:

```python
# src/rag/state.py
from typing import TypedDict, Optional, Literal, Any
from langchain_core.messages import BaseMessage

QueryType = Literal["basic_info", "review_summary", "tmi", "polarity", "recommendation"]

class QueryState(TypedDict, total=False):
    # 입력
    question: str
    messages: list[BaseMessage]         # 멀티턴 히스토리 (Checkpointer가 관리)
    session_id: str

    # 라우팅
    query_type: Optional[QueryType]

    # 캐시
    cache_hit: bool
    cache_source: Optional[Literal["exact", "similar"]]

    # 검색
    retrieved_docs: list[dict]          # {text, metadata, score}
    grounding_docs: list[dict]          # DuckDuckGo 결과
    needs_grounding: bool

    # 생성
    answer: str
    sources: list[dict]                 # 근거 인용 (review_id/url)

    # 관측
    trace_id: str
    latency_ms: dict[str, float]
```

---

## 6. 디버깅 용이성 — 4가지 장치

1. **노드 단독 실행** — 순수 함수라 `pytest`에서 fake state 꽂아 테스트.
2. **Repository 패턴으로 SQL 격리** — pgvector 쿼리(HNSW `ef_search` 튜닝, pre/post-filter 전략)가 자주 바뀌므로 노드 코드에 섞이지 않게.
3. **LangSmith 트레이싱** — `.env`에 키만 넣으면 노드별 입출력·LLM 호출이 전부 시계열로 보임.
4. **Fake Provider** — `providers/llm/fake.py`로 LLM API 안 태우고 그래프 로직만 테스트 → CI 비용 절감.

---

## 7. 1주차 → 2주차 이행 (기획안 §8 리스크 완화)

기획안 §8 "LangGraph 학습 곡선" 리스크 대응과 이 구조가 충돌하지 않도록:

**1주차 (LCEL 선형 체인)**
- `rag/nodes/` 비워둠. 대신 `rag/chains/mvp_chain.py`에 LCEL `retriever | prompt | llm | parser` 선형 체인 1개.
- `providers/`, `prompts/`, `retrievers/`, `db/repositories/`는 **처음부터 분리해서 작성**.
- 목표: end-to-end 돌아가는 Q&A 1종 (기본정보).

**2주차 (LangGraph 리팩토링)**
- `chains/mvp_chain.py`를 조각내서 `rag/nodes/*.py`로 이식.
- `graph.py`에서 StateGraph로 조립.
- `cache_check`, `save_cache`, `route_query`, `ground` 노드 추가.

이행이 "함수 감싸기" 수준으로 단순해지는 게 핵심.

---

## 8. 초기 주의사항 3가지

**(a) QueryState 스키마 설계가 가장 중요한 초기 결정**
바꾸면 모든 노드가 영향받음. 위 §5의 최소 필드는 처음부터 고정.

**(b) Self-Query 메타데이터 ↔ 태깅 화이트리스트 동기화**
Gemma가 뽑는 해시태그 집합 ≠ Self-Query 필터 필드면 무용지물. 상수를 같은 모듈에서 import.

**(c) 캐시 이중 레이어의 임계값 정의**
기획안 §4.1의 `qa_cache`는 `question_hash`(정확) + `question_embedding`(유사) 이중 레이어. **유사도 임계값**(예: cosine ≥ 0.92)을 `settings.py` 상수로 두고 eval 세트로 튜닝. 너무 낮으면 잘못된 캐시 히트, 너무 높으면 히트율 목표(30%) 미달.

---

## 9. 구현 순서 체크리스트

- [ ] `config/settings.py` — env 로드 + LLM/Embedding/Tagger 선택 플래그
- [ ] `providers/base.py` + 각 프로바이더 + 팩토리 (Gemini부터)
- [ ] `db/schema.sql` + `scripts/setup_db.py`
- [ ] `db/repositories/*` — 빈 껍데기 + 타입 힌트
- [ ] `core/types.py` — Movie/Review/TMI Pydantic
- [ ] `ingestion/crawlers/tmdb_client.py` — 영화 30편 메타 수집
- [ ] `ingestion/crawlers/watcha_playwright.py` — 리뷰 수집
- [ ] `ingestion/tagging/` — Gemma 태깅 파이프라인 + 화이트리스트
- [ ] `ingestion/embedding/pipeline.py` + `scripts/reembed.py`
- [ ] `rag/state.py` — QueryState
- [ ] `rag/prompts/basic_info.py` — 1종 먼저
- [ ] `rag/retrievers/self_query.py`
- [ ] `rag/chains/mvp_chain.py` — 1주차 선형 체인
- [ ] `api/routes/chat.py` + `frontend/app.py` — 최소 데모
- [ ] (2주차) `rag/nodes/*` + `rag/graph.py` 로 리팩토링
- [ ] `eval/run_eval.py` — 50문항 평가
