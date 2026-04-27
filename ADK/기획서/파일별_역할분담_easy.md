# 파일별 역할 분담 (Easy 버전)

> 원본: `파일별_역할분담.md` — 기술 용어 기반
> 이 버전: 초보·vibe coder용. "왜 이 파일이 있고, 없으면 뭐가 안 되는지" 중심

---

## 0. 먼저 읽기: 분류 기호 뜻

**영향도 H/L**
- H (높음): 이 파일이 망가지면 **다른 팀원도 일 못 함**. 또는 고치면 다른 파일들도 줄줄이 고쳐야 함.
- L (낮음): 이 파일 문제가 생겨도 **혼자만 피해** 봄.

**복잡도 H/L**
- H (높음): 짜다가 **삽질 많이 할 각**. 외부 API·비동기·상태관리·튜닝 포함.
- L (낮음): **거의 보일러플레이트**. 공식 문서 보고 따라 치면 돌아감.

**🚧 선결 블로커**
= "이게 없으면 아무도 시작 못 함". 1주차 초반에 무조건 먼저 끝내야 함.

---

## 1. 역할 경계 한 줄 요약

- **안도겸**: "질문 들어오면 답 만드는 뇌" 담당 (RAG, 프롬프트, 그래프)
- **이경욱**: "재료 모으고 손질" 담당 (크롤링, 태깅, 임베딩)
- **최정빈**: "창고, 주방 창구" 담당 (DB, API 서버, 프론트 연결)
- **미정**: 셋 다 쓰는 공용 유틸. 먼저 필요한 사람이 최소로 만들고 나중에 확장

---

## 2. 선결 블로커 🚧 — 여기부터 만들어야 함

| 경로 | 책임자 | 왜 먼저 해야 하나 |
| --- | --- | --- |
| `db/schema.sql` | 최정빈 | **DB 설계도**. 테이블 구조가 안 정해지면 아무도 DB 건들 수 없음 |
| `src/core/types.py` | 미정 | "영화는 어떤 필드를 가진 객체인가"를 모든 파일이 참조함. 이게 없으면 리뷰 한 줄 저장하려 해도 모양을 모름 |
| `src/rag/state.py` | 안도겸 | 질문이 노드 사이를 여행할 때 들고 다니는 **데이터 봉투**. 봉투 모양을 모르면 노드를 못 짬 |
| `src/providers/base.py` | 안도겸 | "LLM은 어떤 함수를 가져야 한다"는 **규칙서**. 이게 있어야 Gemini/GPT/Claude를 바꿔 끼울 수 있음 |
| `config/settings.py` | 미정 | API 키·DB 주소 같은 **환경변수 읽는 파일**. 이게 없으면 Gemini 호출 자체가 안 됨 |
| `pyproject.toml` | 미정 | "이 프로젝트는 langchain·langgraph·fastapi를 씁니다" **라이브러리 목록**. 이거 없으면 `pip install` 부터 안 됨 |

---

## 3. 전체 분류 (쉬운 설명)

### `config/` — 설정값 모음집

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `config/settings.py` | 미정 | H/L | API 키, DB 주소, "어떤 LLM 쓸거야?" 같은 환경변수를 **한 곳에서 읽어주는 창구**. 모든 파일이 여기 와서 설정을 꺼내감 🚧 |
| `config/model_registry.py` | 안도겸 | H/L | "Gemini 기본 temperature는 0.3, max_token은 1024" 같은 **모델별 기본 옵션 메모장**. 모델 갈아끼울 때 여기만 수정 |

### `src/core/` — 팀 공용 유틸

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `src/core/types.py` | 미정 | H/L | "영화는 어떤 필드를 가진 객체다"를 정의한 **데이터 모양 사전**. 세 팀원이 같은 모양을 공유해야 DB·API·RAG가 서로 말이 통함 🚧 |
| `src/core/exceptions.py` | 미정 | L/L | "크롤러 실패"는 `CrawlerError`로 부르자 같은 **에러 이름 통일장**. 디버깅할 때 편해짐 |
| `src/core/logging.py` | 미정 | L/L | 로그 찍는 방식 통일. 터미널에 출력 포맷 맞춰주는 역할 |

### `src/providers/` — 모델 꽂는 콘센트

이 폴더가 **"Gemini → GPT 교체 한 줄로 가능"의 핵심**. 노드 코드는 `get_llm()`만 부르고, 이 폴더가 어떤 모델을 뽑아줄지 알아서 결정.

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `src/providers/base.py` | 안도겸 | H/L | "LLM이라면 최소한 `invoke()`·`stream()` 함수는 있어야 한다"는 **규격 선언서**. 이 규격만 맞추면 어떤 모델도 붙일 수 있음 🚧 |
| `src/providers/llm/__init__.py` | 안도겸 | H/L | `.env` 읽어서 "너는 Gemini 쓸 거지?" 하고 맞는 모델을 **자판기처럼 뽑아주는** 함수 |
| `src/providers/llm/gemini.py` | 안도겸 | L/L | Gemini를 규격에 맞춰 감싼 어댑터 |
| `src/providers/llm/openai.py` | 안도겸 | L/L | GPT-4o 어댑터 |
| `src/providers/llm/claude.py` | 안도겸 | L/L | Claude 어댑터 |
| `src/providers/llm/fake.py` | 안도겸 | L/L | **테스트용 가짜 LLM**. 진짜 API 안 부르고 미리 정해둔 답 돌려줌 → 돈·시간 절약 |
| `src/providers/embedding/__init__.py` | 안도겸 | H/L | 임베딩 모델(문장→숫자벡터) 자판기 |
| `src/providers/embedding/gemini.py` | 안도겸 | L/L | Gemini 임베딩 어댑터 |
| `src/providers/embedding/openai.py` | 안도겸 | L/L | OpenAI 임베딩 어댑터 |
| `src/providers/tagger/__init__.py` | 이경욱 | H/L | 태깅 모델(Gemma 등) 자판기 |
| `src/providers/tagger/gemma_local.py` | 이경욱 | L/H | **내 컴퓨터에서 Gemma 직접 돌리는** 파일. 모델 다운로드·메모리 관리·타임아웃이 까다로움 |
| `src/providers/tagger/hf_endpoint.py` | 이경욱 | L/L | HuggingFace 클라우드에 있는 모델 쓸 때 쓰는 파일 |

### `src/db/` — 데이터 창고

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `src/db/client.py` | 최정빈 | H/L | Supabase(DB)에 접속하는 **커넥션을 한 번만 만들어서 앱 전체가 공유**하게 해주는 파일 |
| `src/db/schema.sql` | 최정빈 | H/H | **DB 설계도**. "영화 테이블, 리뷰 테이블이 있고 각각 어떤 컬럼을 가진다"를 전부 적은 SQL 🚧 |
| `src/db/migrations/` | 최정빈 | H/H | DB 구조 바꿀 때 "이 순서대로 바꿔라"는 대본 모음. 서비스 안 끊기게 바꾸는 게 까다로움 |
| `src/db/repositories/movies_repo.py` | 최정빈 | L/L | "영화 하나 꺼내", "영화 넣어" 같은 **영화 관련 DB 함수 모음** |
| `src/db/repositories/reviews_repo.py` | 최정빈 | H/L | 리뷰용 DB 함수. 세 팀원이 가장 많이 갖다 씀 |
| `src/db/repositories/tmi_repo.py` | 최정빈 | L/L | TMI용 DB 함수 |
| `src/db/repositories/cache_repo.py` | 최정빈 | H/H | **캐시 저장소**. "같은 질문 또 들어오면 DB에 저장해둔 답 바로 돌려주기" 담당. 속도의 핵심 |
| `src/db/repositories/log_repo.py` | 최정빈 | L/L | "누가 언제 뭐 물었는지" 기록장 |

### `src/ingestion/` — 재료 수집·손질 공장

오프라인으로 한 번씩 돌리는 **배치 작업**. 서비스 돌아갈 때는 건들지 않음.

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `src/ingestion/crawlers/tmdb_client.py` | 이경욱 | L/L | **TMDB에서 영화 정보 긁어오는** 스크립트. 제목·감독·줄거리·포스터 등 |
| `src/ingestion/crawlers/watcha_playwright.py` | 이경욱 | L/H | **왓챠에서 리뷰 긁어오는** 스크립트. 왓챠가 차단하면 이걸로 다 막히니 조심스럽게 |
| `src/ingestion/crawlers/duckduckgo_client.py` | 최정빈 | L/L | 덕덕고 검색 결과 긁어오는 스크립트 |
| `src/ingestion/tagging/prompts.py` | 이경욱 | H/L | "이 리뷰에서 `#연기호평` 같은 해시태그 뽑아줘"라고 Gemma에게 시키는 **지시문**. 여기의 태그 목록이랑 검색 필터의 태그 목록이 무조건 같아야 함 |
| `src/ingestion/tagging/pipeline.py` | 이경욱 | L/H | 리뷰 수천 개를 Gemma에 차례차례 돌려 해시태그 다는 **일괄 처리 공장** |
| `src/ingestion/embedding/pipeline.py` | 이경욱 | H/H | 리뷰·TMI 문장을 **숫자 벡터로 바꿔서 DB에 넣는 공장**. 임베딩 모델 바꾸면 전체 다시 돌려야 함 |
| `src/ingestion/run.py` | 이경욱 | L/L | 터미널에서 `python run.py --stage crawl` 식으로 단계별 실행하는 **스위치 패널** |

### `src/rag/` — 질문에 답하는 뇌

질문이 들어왔을 때 실행되는 **온라인 파이프라인**. 사용자가 기다리고 있으므로 빨라야 함.

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `src/rag/state.py` | 안도겸 | H/L | 질문이 여행하면서 들고 다니는 **데이터 봉투 모양**. (질문/분류/검색결과/답/출처 등) 🚧 |
| `src/rag/graph.py` | 안도겸 | H/H | **전체 흐름도를 코드로 그린 파일**. "질문→캐시→분류→검색→답생성→저장" 이 파일만 봐도 시스템 동작 한눈에 이해 가능 |
| `src/rag/checkpointer.py` | 안도겸 | L/H | 멀티턴 대화용 **기억 장치**. "아까 말한 그 영화" 같은 문맥 유지 |
| `src/rag/nodes/cache_check.py` | 안도겸 | L/H | "이 질문 전에 받아봤나?" 먼저 확인. 있으면 바로 답 돌려주고 끝 → 속도 쾌적 |
| `src/rag/nodes/route_query.py` | 안도겸 | L/H | "이 질문 종류가 뭐야?" **5종 분류** (기본정보/리뷰/TMI/호불호/추천) |
| `src/rag/nodes/retrieve.py` | 안도겸 | H/H | DB에서 **관련 리뷰·TMI 찾아오는** 노드. 검색 품질의 심장 |
| `src/rag/nodes/ground.py` | 최정빈 | L/H | DB에 없는 정보면 **덕덕고로 실시간 검색**해와서 보충 |
| `src/rag/nodes/generate.py` | 안도겸 | L/H | 찾아온 자료를 LLM에 넣어 **최종 답 만들기** |
| `src/rag/nodes/save_cache.py` | 안도겸 | L/L | 방금 만든 답을 캐시에 저장. 다음번엔 빨라짐 |
| `src/rag/retrievers/self_query.py` | 안도겸 | H/H | "봉준호 감독 4점 이상 리뷰 중 비슷한 거"처럼 **필터+의미검색 동시** 수행하는 똑똑한 검색기 |
| `src/rag/retrievers/hybrid.py` | 안도겸 | L/H | 키워드 검색과 벡터 검색 섞어 쓰는 옵션 |
| `src/rag/prompts/router.py` | 안도겸 | L/H | "아래 질문이 5종 중 뭐야?" 분류 지시문 + 예시 몇 개 |
| `src/rag/prompts/basic_info.py` | 안도겸 | L/L | 기본정보 질문용 답변 지시문 템플릿 |
| `src/rag/prompts/review_summary.py` | 안도겸 | L/L | 리뷰 요약용 지시문 |
| `src/rag/prompts/tmi.py` | 안도겸 | L/L | TMI 답변용 지시문 |
| `src/rag/prompts/polarity.py` | 안도겸 | L/H | 호불호 분석용. "상반된 리뷰 대조" 같은 까다로운 로직 |
| `src/rag/prompts/recommendation.py` | 안도겸 | L/L | 추천 답변용 지시문 |
| `src/rag/parsers/answer_parser.py` | 안도겸 | L/L | LLM이 뱉은 답에서 **"답 본문"과 "출처 링크"를 깔끔히 분리**하는 파서 |
| `src/rag/chains/mvp_chain.py` | 안도겸 | L/H | **1주차용 간단 버전**. LangGraph 배우기 전 "그냥 쭉 흘리는 파이프라인". 2주차에 `nodes/`로 쪼개 이식 |

### `src/api/` — 프론트와 뇌 사이의 창구

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `src/api/main.py` | 최정빈 | H/L | FastAPI **서버 시작 지점**. "라우터 등록하고 서버 켜" |
| `src/api/schemas.py` | 최정빈 | H/L | 프론트↔백엔드 사이 **주고받을 JSON 모양 약속서**. 이거 바뀌면 프론트도 같이 고쳐야 함 |
| `src/api/routes/chat.py` | 최정빈 | H/H | `/chat` 엔드포인트. 질문 받아 RAG 돌리고 **답을 한 글자씩 실시간 스트리밍**으로 보냄. 가장 까다로움 |
| `src/api/routes/health.py` | 최정빈 | L/L | "서버 살아있나요?" 체크용 |
| `src/api/dependencies.py` | 최정빈 | L/H | 라우터에 그래프·세션·인증 주입하는 **접착제** |

### `src/eval/` — 품질 측정 자

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `src/eval/eval_set.yaml` | 미정 | L/L | "이 질문엔 이런 답이 나와야 함" **50개 정답지**. 품질 측정의 기준 |
| `src/eval/metrics.py` | 안도겸 | L/H | 정답률·출처제시율·응답속도 계산기 |
| `src/eval/run_eval.py` | 안도겸 | L/L | "자 지금 시스템 품질 좀 재볼까?" 실행 버튼 |

### `tests/` — 안전망

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `tests/unit/*` | 각 파일 owner | L/L~L/H | 파일 하나하나 잘 돌아가는지 확인. **만든 사람이 자기 테스트 작성** 원칙 |
| `tests/integration/test_graph_end_to_end.py` | 안도겸 | L/H | **가짜 LLM**으로 전체 흐름 한 번 돌려보기. 돈 안 씀 |
| `tests/integration/test_ingestion_pipeline.py` | 이경욱 | L/L | 영화 1편으로 크롤링→태깅→임베딩→DB저장 전체 검증 |
| `tests/fixtures/sample_state.json` | 미정 | L/L | 테스트용 가짜 데이터 |

### `scripts/` — 가끔 돌리는 유틸 스크립트

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `scripts/setup_db.py` | 최정빈 | L/L | "처음 DB 만들기" 최초 1회 실행 스크립트 |
| `scripts/benchmark_retriever.py` | 안도겸 | L/H | 벡터 검색 옵션 바꿔가며 **속도 vs 정확도 측정** |
| `scripts/reembed.py` | 안도겸 | H/H | **임베딩 모델 교체 시 전체 벡터 다시 계산**. 서비스 안 끊기게 조심스럽게 교체 |

### `frontend/` — 사용자가 보는 화면

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `frontend/app.py` | 최정빈 | L/L | Streamlit로 만든 **채팅 UI**. `/chat`에 질문 보내고 답 받아 화면에 뿌림 |

### 루트 파일

| 경로 | 책임자 | 영향/복잡 | 설명 |
| --- | --- | --- | --- |
| `README.md` | 안도겸 | L/L | "이 프로젝트 뭐고 어떻게 실행하나" 설명서 |
| `pyproject.toml` | 미정 | H/L | "이 프로젝트는 langchain, langgraph, fastapi를 씁니다" **라이브러리 목록**. 이거 없으면 `pip install`부터 못 함 🚧 |
| `.env.example` | 안도겸 | H/L | 환경변수 템플릿. 복사해서 `.env`로 만들고 본인 API 키 채워넣는 용도 |

---

## 4. 초보자가 기억하면 좋은 3가지

### (1) 🚧 블로커 6개가 제일 먼저, 나머지는 병렬
먼저 블로커들만 "최소한 돌아가는 상태"로 만들면 그때부터 세 명이 각자 자기 영역을 동시에 만들 수 있음. 순서가 중요함.

### (2) "어디를 고쳐야 할지" 찾는 요령
- 사용자가 보는 화면 문제 → `frontend/`
- "서버 응답이 이상해" → `src/api/routes/chat.py`
- "답이 틀렸어" → `src/rag/prompts/*` 또는 `src/rag/nodes/generate.py`
- "검색이 엉뚱한 걸 가져와" → `src/rag/retrievers/self_query.py`
- "DB에 데이터가 없어" → `src/ingestion/*`
- "모델을 바꾸고 싶어" → `.env` + `src/providers/*`

### (3) 모델 교체 = `.env` 한 줄
이 구조의 핵심 이점. Gemini에서 GPT로 바꾸려면 `.env`의 `LLM_PROVIDER=openai` 한 줄만 수정. 노드 코드는 건들지 않음. 이게 가능한 이유는 `src/providers/` 폴더가 모든 외부 모델 호출을 자판기처럼 추상화해뒀기 때문.
