"""
전역 설정 로더.

모든 환경변수를 한 곳에서 읽어 Pydantic으로 타입 검증한다.
다른 모듈은 반드시 이 `settings` 싱글턴을 통해서만 설정을 조회한다.

사용 예:
    from config.settings import settings
    llm_name = settings.LLM_PROVIDER

주의:
- API 키가 비어있어도 앱은 실행됨. 실제 LLM 호출 시점에 에러 남.
- `.env` 파일이 없으면 시스템 환경변수에서 읽음. 둘 다 없으면 기본값 사용.
"""
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """.env 또는 시스템 환경변수에서 설정을 로드."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",        # .env에 정의 안 된 키는 무시
        case_sensitive=True,
    )

    # ========== 모델 선택 (Phase 1+) ==========
    # providers 팩토리가 이 값을 읽어 구현체를 뽑아옴.
    # .env에서 이 값만 바꾸면 모델이 교체됨 (코드 수정 불필요).
    LLM_PROVIDER: Literal["gemini", "openai", "claude", "fake"] = "gemini"
    EMBEDDING_PROVIDER: Literal["gemini", "openai"] = "gemini"
    TAGGER_PROVIDER: Literal["gemma_local", "hf_endpoint"] = "gemma_local"

    # ========== 모델 파라미터 기본값 ==========
    # provider별 세밀 튜닝은 `config/model_registry.py`에서 override.
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2048
    EMBEDDING_DIMENSION: int = 768  # Gemini text-embedding-004 기준

    # ========== API 키 ==========
    # 발급 후 .env에 기입. settings.py 직접 수정 금지.
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    HUGGINGFACE_API_KEY: str = ""

    # ========== Supabase (Phase 2 후반부터) ==========
    # 지금은 비워둬도 앱 실행에 문제 없음.
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    # pgvector 직접 연결용 (postgresql://user:pass@host/db)
    SUPABASE_DB_URL: str = ""

    # ========== 외부 API ==========
    # TMDB: https://www.themoviedb.org/settings/api
    TMDB_API_KEY: str = ""

    # ========== 캐시 설정 (Phase 4) ==========
    # 질문 embedding 유사도가 이 값 이상이면 캐시 히트로 처리.
    # 너무 낮으면 잘못된 답 재사용, 너무 높으면 히트율 목표(기획안 §7의 30%) 미달.
    # eval 세트로 튜닝 권장.
    CACHE_SIMILARITY_THRESHOLD: float = 0.92

    # ========== 검색 설정 ==========
    RETRIEVER_TOP_K: int = 6
    GROUNDING_ENABLED: bool = True

    # ========== 로깅 / 관측 ==========
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # LangSmith 트레이싱 (Phase 3+ 디버깅에 강력 추천)
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "movie-docent"

    # ========== 앱 환경 ==========
    APP_ENV: Literal["dev", "staging", "prod"] = "dev"


# 전역 싱글턴.
# 다른 모듈은 `from config.settings import settings`로 접근.
settings = Settings()
