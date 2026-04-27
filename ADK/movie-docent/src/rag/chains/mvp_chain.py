"""
MVP RAG 체인 — Phase 2 첫 end-to-end ⭐

구조: fake_retrieve → basic_info_prompt → llm → str
- DB 없이 `tests/fixtures/sample_reviews.json`에서 리뷰 로드
- LangChain Expression Language(LCEL)로 한 줄에 엮음
- 실행: `python -m rag.chains.mvp_chain "기생충 감독이 누구야?"`

이 파일이 동작하면 = Gemini가 살아 있고, 프롬프트·팩토리가 정상.
Phase 3에서 `fake_retrieve`만 self-query 리트리버로 교체하면 됨.

주의:
- 실제 호출에는 `.env`의 `GEMINI_API_KEY` 필요
- API 키 없을 때는 `LLM_PROVIDER=fake`로 바꿔서 import만 검증
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough

from providers.llm import get_llm
from rag.prompts.basic_info import basic_info_prompt


# ============================================================
# Fixture 경로 — src/rag/chains → repo root → tests/fixtures
# ============================================================
# __file__ → .../src/rag/chains/mvp_chain.py
# parents[0] = chains, [1] = rag, [2] = src, [3] = movie-docent (repo root)
FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sample_reviews.json"
)


# ============================================================
# Fake retriever — Phase 3에서 self-query로 교체될 자리
# ============================================================

def _load_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(
            f"Fixture not found: {FIXTURE_PATH}\n"
            f"Phase 2는 fixture 없이 못 돌아간다. tests/fixtures/sample_reviews.json 확인."
        )
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def fake_retrieve(question: str) -> str:
    """
    질문 무시. fixture의 영화 정보 + 리뷰 3건을 프롬프트에 넣을 텍스트로 반환.

    Phase 3에서 `rag.retrievers.self_query.SelfQueryRetriever`로 교체.
    그때 시그니처는 (question: str) -> list[RetrievedDoc]이 됨.
    """
    data = _load_fixture()
    movie = data["movie"]
    reviews = data["reviews"]

    lines = [
        "[영화 정보]",
        f"- 제목: {movie['title']}",
        f"- 감독: {movie['director']}",
        f"- 개봉: {movie['release_date']}",
        f"- 장르: {movie['genre']}",
        f"- 출연: {movie['cast_members']}",
        f"- TMDB 평점: {movie['tmdb_rating']}",
        f"- 줄거리: {movie['overview']}",
        "",
        "[리뷰]",
    ]
    for r in reviews:
        lines.append(
            f"- {r['reviewer_nickname']} (★{r['rating']}, 좋아요 {r['likes_count']}): {r['content']}"
        )
    return "\n".join(lines)


# ============================================================
# 체인 빌드
# ============================================================

def build_mvp_chain() -> Runnable:
    """
    LCEL 체인:
        {context: fake_retrieve, question: passthrough}
        → basic_info_prompt
        → llm.invoke (PromptValue → str)

    각 단계 출력 타입:
        input        : str (사용자 질문)
        dict 단계 후  : {"context": str, "question": str}
        prompt 단계 후 : ChatPromptValue
        llm 단계 후    : str (최종 답변)
    """
    llm = get_llm()

    # PromptValue → str 변환 + LLMProvider 호출
    # 우리 ABC는 PromptInput(str | list[dict])만 받으므로 to_string()으로 직렬화.
    def llm_call(prompt_value) -> str:
        return llm.invoke(prompt_value.to_string())

    chain: Runnable = (
        {
            "context": RunnableLambda(fake_retrieve),
            "question": RunnablePassthrough(),
        }
        | basic_info_prompt
        | RunnableLambda(llm_call)
    )
    return chain


# ============================================================
# CLI 진입점
# ============================================================

def main() -> None:
    question = (
        " ".join(sys.argv[1:]).strip()
        if len(sys.argv) > 1
        else "기생충에 대해 알려줘"
    )

    print(f"\n[질문] {question}\n")

    chain = build_mvp_chain()
    answer = chain.invoke(question)

    print("[답변]")
    print(answer)
    print()


if __name__ == "__main__":
    main()
