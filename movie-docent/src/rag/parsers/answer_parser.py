"""
answer_parser — LLM 답변에서 출처 부분을 분리.

기획안 §7 "출처 제시율 90% 목표"용. 답변 본문과 출처를 분리해서
state.answer (본문) + state.sources (Citation 리스트)로 저장.

휴리스틱:
  - 답변 마지막 단락에 '출처:' 또는 '참고:' 마커가 있으면 그 이후를 출처 텍스트로 인식
  - retrieved_docs를 같이 주면 본문에 인용된 source_id를 매칭해 정확한 Citation 생성
  - docs가 없거나 매칭 실패 시 출처 텍스트의 URL 정도만 best-effort 흡수

Phase 4에서 더 정확하게: LLM이 [^1] 같은 footnote ID를 직접 박게 하는 방식 검토.
"""
from __future__ import annotations

import re

from core.types import Citation, RetrievedDoc


SOURCE_MARKER = re.compile(
    r"\n\s*(?:출처|참고|Source|References?)\s*[:：]",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://\S+")


def _split_body_and_source_text(answer: str) -> tuple[str, str]:
    """답변 텍스트를 본문과 출처 텍스트로 분리."""
    m = SOURCE_MARKER.search(answer)
    if not m:
        return answer.strip(), ""
    body = answer[: m.start()].rstrip()
    source_text = answer[m.end():].strip()
    return body, source_text


def _match_docs_to_citations(
    full_answer: str,
    docs: list[RetrievedDoc],
) -> list[Citation]:
    """
    답변 본문에 등장하는 doc을 Citation으로 변환.
    매칭 기준 (any of):
      - source#source_id 직접 등장 (예: "review#3")
      - metadata.title이 답변에 등장
      - metadata.reviewer_nickname이 답변에 등장
    """
    citations: list[Citation] = []
    for d in docs:
        ref_str = f"{d.source}#{d.source_id}"
        title = (d.metadata or {}).get("title")
        nick = (d.metadata or {}).get("reviewer_nickname")
        url = (d.metadata or {}).get("source_url")

        mentioned = False
        if ref_str in full_answer:
            mentioned = True
        elif title and title in full_answer:
            mentioned = True
        elif nick and nick in full_answer:
            mentioned = True

        if mentioned:
            citations.append(Citation(
                source=d.source,
                source_id=d.source_id,
                snippet=d.text[:120],
                url=url,
            ))
    return citations


def split_answer_and_sources(
    answer: str,
    docs: list[RetrievedDoc] | None = None,
) -> tuple[str, list[Citation]]:
    """
    답변에서 본문과 출처 인용 리스트를 분리.

    Args:
        answer: LLM 원본 답변 문자열
        docs: 같이 들어간 retrieved_docs (있으면 정확도↑)

    Returns:
        (본문, Citation 리스트)
    """
    body, source_text = _split_body_and_source_text(answer)

    citations: list[Citation] = []

    # 1차: docs 매칭 (가장 정확)
    if docs:
        citations = _match_docs_to_citations(answer, docs)

    # 2차: 매칭 실패 시 출처 텍스트의 URL이라도 흡수
    if not citations and source_text:
        urls = URL_RE.findall(source_text)
        for i, u in enumerate(urls):
            citations.append(Citation(
                source="external",
                source_id=i,
                snippet=source_text[:120],
                url=u,
            ))

    return body, citations


__all__ = ["split_answer_and_sources"]
