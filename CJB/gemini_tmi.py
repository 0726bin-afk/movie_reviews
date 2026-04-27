"""
gemini_tmi.py
=============
나무위키 → 섹션명 기반 카테고리 매핑 → Gemini TMI 추출 → Supabase 저장.

groq_tmi.py와 동일한 로직, 모델만 Gemini 2.5 Flash로 교체.

흐름:
  1. 나무위키 목차에서 섹션명 추출
  2. Gemini: 섹션명 → 카테고리 매핑 (1회 호출)
  3. 카테고리별 해당 섹션 내용만 추출 (글자 수 제한 없음)
  4. Gemini: 섹션 내용 → TMI 추출 (카테고리당 1회 호출)
  5. DB 저장

설치:
  pip install google-generativeai

실행:
  python gemini_tmi.py --title "살인의 추억" --dry-run
  python gemini_tmi.py --title "살인의 추억"
  python gemini_tmi.py                         # 전체 영화 (빈 카테고리만)
  python gemini_tmi.py --overwrite             # 기존 데이터 덮어쓰기
"""

import os
import re
import time
import warnings
import argparse
import urllib.parse
import requests
import psycopg2
import psycopg2.extras
from bs4 import BeautifulSoup
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=FutureWarning)
import google.generativeai as genai

load_dotenv()

# ============================================================
#  DB
# ============================================================
DB_CONFIG = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT", "5432"),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


# ============================================================
#  Gemini 클라이언트
# ============================================================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
GEMINI_MODEL  = "gemini-2.5-flash"
gemini_model  = genai.GenerativeModel(GEMINI_MODEL)

API_CALL_INTERVAL = 4  # 초 (분당 15회 제한 → 4초 간격)

ALL_CATEGORIES = ["촬영지", "OST", "비하인드", "옥에티", "캐스팅비화"]

CATEGORY_DESC = {
    "촬영지":     "영화를 촬영한 실제 장소, 로케이션, 세트장",
    "OST":        "영화 사운드트랙, 삽입곡, 음악",
    "비하인드":   "촬영 비하인드, 제작 뒷이야기, 에피소드",
    "옥에티":     "영화 속 고증 오류, 연속성 오류, 실수",
    "캐스팅비화": "배우 캐스팅 과정, 오디션, 섭외 비화",
}

# ============================================================
#  나무위키 URL 오버라이드 (자동 탐지 실패 영화)
# ============================================================
NAMU_URL_OVERRIDES: dict[str, str] = {
    "리얼":              "https://namu.wiki/w/%EB%A6%AC%EC%96%BC(%EC%98%81%ED%99%94)",
    "매드맥스: 분노의 도로": "https://namu.wiki/w/%EB%A7%A4%EB%93%9C%20%EB%A7%A5%EC%8A%A4:%20%EB%B6%84%EB%85%B8%EC%9D%98%20%EB%8F%84%EB%A1%9C",
    "메멘토":             "https://namu.wiki/w/%EB%A9%94%EB%A9%98%ED%86%A0",
    "베테랑 2":           "https://namu.wiki/w/%EB%B2%A0%ED%85%8C%EB%9E%912",
    "어쩔 수가 없다":     "https://namu.wiki/w/%EC%96%B4%EC%A9%94%EC%88%98%EA%B0%80%EC%97%86%EB%8B%A4",
    "올드보이":           "https://namu.wiki/w/%EC%98%AC%EB%93%9C%EB%B3%B4%EC%9D%B4(2003)",
    "인어공주 (실사)":    "https://namu.wiki/w/%EC%9D%B8%EC%96%B4%EA%B3%B5%EC%A3%BC(2023)",
    "조커":              "https://namu.wiki/w/%EC%A1%B0%EC%BB%A4(2019)",
}

# ============================================================
#  크롤링 설정
# ============================================================
SECTION_BLACKLIST = [
    "줄거리", "개요", "등장인물", "평가", "흥행", "수상", "역대",
    "관련 문서", "외부 링크", "둘러보기", "같이 보기", "프롤로그",
    "논란", "사건 사고", "시놉시스", "평론가",
]

SUB_PAGE_BLACKLIST = ["줄거리", "흥행", "등장인물", "수상", "평가"]

CRAWL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_TOC_RE      = re.compile(r"^\.\s+\S")
MIN_LINE_LEN = 20


# ============================================================
#  페이지 fetch
# ============================================================
def fetch_text(url: str) -> str:
    try:
        res = requests.get(url, headers=CRAWL_HEADERS, timeout=10)
        if res.status_code != 200:
            return ""
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if len(l.strip()) > 5]
        return "\n".join(lines)
    except Exception:
        return ""


def _namu_url(title: str) -> str:
    return f"https://namu.wiki/w/{urllib.parse.quote(title)}"


def fetch_namu_main(movie_title: str) -> tuple[str, str]:
    # 오버라이드 URL이 있으면 우선 사용
    if movie_title in NAMU_URL_OVERRIDES:
        url  = NAMU_URL_OVERRIDES[movie_title]
        text = fetch_text(url)
        if len(text) > 3000:
            return text, url
        print(f"  ⚠️ 오버라이드 URL 실패: {url}")

    for candidate in [
        f"{movie_title}(영화)",
        f"{movie_title}(한국 영화)",
        f"{movie_title}(미국 영화)",
        f"{movie_title}(일본 영화)",
        f"{movie_title}(애니메이션)",
        movie_title,
    ]:
        url  = _namu_url(candidate)
        text = fetch_text(url)
        if len(text) > 3000:
            return text, url
        time.sleep(0.3)
    return "", ""


# ============================================================
#  TOC / 섹션 탐지
# ============================================================
def _find_toc_end(lines: list) -> int:
    toc_end = 0
    i = 0
    while i < len(lines):
        if _TOC_RE.match(lines[i]):
            j = i + 1
            while j < len(lines) and _TOC_RE.match(lines[j]):
                j += 1
            if j - i >= 3:
                toc_end = j
            i = j
        else:
            i += 1
    return toc_end


def get_section_names(full_text: str) -> list[str]:
    lines   = full_text.splitlines()
    toc_end = _find_toc_end(lines)
    names   = []
    for line in lines[:toc_end]:
        stripped = line.strip()
        if _TOC_RE.match(stripped):
            name = re.sub(r"^\.\s+", "", stripped)
            name = re.sub(r"^[\d\.]+\s*", "", name).strip()
            if name and len(name) >= 2:
                names.append(name)
    return names


def find_sub_pages(full_text: str, movie_title: str) -> dict[str, str]:
    title_variants = [
        f"{movie_title}(영화)", f"{movie_title}(한국 영화)",
        f"{movie_title}(미국 영화)", f"{movie_title}(일본 영화)",
        f"{movie_title}(애니메이션)", movie_title,
    ]
    sub_pages = {}
    for line in full_text.splitlines():
        for variant in title_variants:
            for sub in re.findall(re.escape(variant) + r"/(\S+)", line):
                if sub not in sub_pages:
                    sub_pages[sub] = _namu_url(f"{variant}/{sub}")
    return sub_pages


def extract_section(full_text: str, section_name: str) -> str:
    """섹션 이름에 해당하는 본문 전체 추출. 완전 일치 우선, 부분 일치 폴백."""
    lines   = full_text.splitlines()
    toc_end = _find_toc_end(lines)
    body    = lines[toc_end:]

    start_idx = -1
    sec_lower = section_name.lower()

    # 1차: 완전 일치
    for i, line in enumerate(body):
        if line.strip().lower() == sec_lower:
            start_idx = i
            break

    # 2차: 부분 일치
    if start_idx == -1:
        for i, line in enumerate(body):
            stripped = line.strip()
            if 2 < len(stripped) <= 80 and sec_lower in stripped.lower():
                start_idx = i
                break

    if start_idx == -1:
        return ""

    collected = []
    for line in body[start_idx + 1:]:
        stripped = line.strip()
        if _TOC_RE.match(stripped):
            break
        if len(stripped) >= MIN_LINE_LEN:
            collected.append(stripped)

    return "\n".join(collected)


def extract_body(full_text: str) -> str:
    lines   = full_text.splitlines()
    toc_end = _find_toc_end(lines)
    return "\n".join(
        l.strip() for l in lines[toc_end:]
        if len(l.strip()) >= MIN_LINE_LEN
    )


# ============================================================
#  Gemini API 호출 공통 함수
# ============================================================
def _call_gemini(prompt: str) -> str:
    """Gemini API 호출. rate limit 시 대기 후 재시도. 빈 문자열 반환 시 실패."""
    for attempt in range(3):
        try:
            resp   = gemini_model.generate_content(prompt)
            result = resp.text.strip()
            time.sleep(API_CALL_INTERVAL)  # 분당 15회 제한 준수
            return result
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                if "day" in err.lower() or "daily" in err.lower():
                    print(f"    ❌ 일일 한도 초과. 내일 재시도 필요.")
                    return ""
                wait = 60
                print(f"    rate limit → {wait}초 대기 (attempt {attempt+1}/3)...")
                time.sleep(wait)
            else:
                print(f"    Gemini 오류: {e}")
                return ""
    return ""


# ============================================================
#  Gemini: 섹션명 → 카테고리 매핑 (1회 호출)
# ============================================================
def map_sections_to_categories(movie_title: str, section_names: list[str]) -> dict[str, list[str]]:
    """
    나무위키 섹션명 목록을 보고 각 카테고리에 해당하는 섹션을 Gemini가 분류.
    반환: { "촬영지": ["로케이션/소품 및 고증"], "비하인드": ["제작 과정", "후일담"], ... }
    """
    if not section_names:
        return {}

    filtered = [
        s for s in section_names
        if not any(bl.lower() in s.lower() for bl in SECTION_BLACKLIST)
    ]
    if not filtered:
        return {}

    sections_str   = "\n".join(f"- {s}" for s in filtered)
    categories_str = "\n".join(f"- {cat}: {desc}" for cat, desc in CATEGORY_DESC.items())

    prompt = f"""영화 '{movie_title}'의 나무위키 목차 섹션 목록입니다.
각 섹션이 아래 TMI 카테고리 중 어디에 해당하는지 분류해줘.

[TMI 카테고리]
{categories_str}

[섹션 목록]
{sections_str}

규칙:
- 각 카테고리에 해당하는 섹션명을 콤마로 나열 (섹션명 그대로 복사)
- 해당 섹션이 없으면 "없음"
- 반드시 아래 5개 카테고리 모두 한 줄씩 답해야 함
- 형식 외 다른 말 하지 말 것

출력 형식:
촬영지: 섹션명1, 섹션명2
OST: 없음
비하인드: 섹션명3, 섹션명4
옥에티: 없음
캐스팅비화: 섹션명5"""

    result = _call_gemini(prompt)
    if not result:
        return {}

    mapping = {}
    for line in result.splitlines():
        for cat in ALL_CATEGORIES:
            if line.startswith(cat + ":"):
                val = line[len(cat) + 1:].strip()
                if val and val != "없음":
                    secs = [s.strip() for s in val.split(",") if s.strip()]
                    if secs:
                        mapping[cat] = secs
                break
    return mapping


# ============================================================
#  Gemini: 섹션 내용 → TMI 추출
# ============================================================
def ask_gemini(movie_title: str, source_text: str, category: str) -> list[str]:
    """
    해당 카테고리 섹션 내용에서 TMI만 추출.
    반환: TMI 문자열 리스트 (없으면 [])
    """
    prompt = f"""아래는 영화 '{movie_title}'의 나무위키 '{category}' 관련 섹션 내용입니다.
이 내용을 바탕으로 '{category}' TMI를 정리해줘.

'{category}'의 의미: {CATEGORY_DESC[category]}

규칙:
- TMI 하나당 한 줄, 2~4문장으로 요약
- 관련 내용이 전혀 없으면 첫 줄에 "없음"이라고만 답해
- 번호나 기호 없이 줄글로

[나무위키 내용]
{source_text}"""

    result = _call_gemini(prompt)
    if not result:
        return []
    if result.startswith("없음"):
        return []

    return [l.strip() for l in result.splitlines() if len(l.strip()) >= MIN_LINE_LEN]


# ============================================================
#  영화 한 편 TMI 수집
# ============================================================
def collect_tmi(movie_title: str, verbose: bool = True) -> dict[str, list[str]]:
    # 1. 나무위키 메인 페이지 fetch
    main_text, main_url = fetch_namu_main(movie_title)
    if not main_text:
        if verbose:
            print("  ❌ 나무위키 페이지를 찾을 수 없음")
        return {}

    # 2. 목차 섹션명 추출
    section_names = get_section_names(main_text)
    if verbose:
        print(f"  섹션 목록: {section_names}")

    # 3. Gemini: 섹션명 → 카테고리 매핑 (1회 호출)
    if verbose:
        print("  [Gemini] 섹션 → 카테고리 매핑 중...")
    mapping = map_sections_to_categories(movie_title, section_names)
    if verbose:
        for cat, secs in mapping.items():
            print(f"    {cat}: {secs}")

    # 4. 서브페이지 수집
    sub_texts = {}
    for sub_name, sub_url in find_sub_pages(main_text, movie_title).items():
        if any(bl.lower() in sub_name.lower() for bl in SUB_PAGE_BLACKLIST):
            if verbose:
                print(f"  서브 스킵: /{sub_name}")
            continue
        if verbose:
            print(f"  서브 fetch: /{sub_name}")
        sub_text = fetch_text(sub_url)
        if sub_text:
            sub_texts[sub_name] = extract_body(sub_text)
        time.sleep(0.3)

    # 5. 카테고리별 TMI 추출
    result = {}
    for category in ALL_CATEGORIES:
        if verbose:
            print(f"\n  [{category}] 섹션 내용 수집 중...")

        parts = []

        # 매핑된 섹션 내용 추출
        if category in mapping:
            for sec_name in mapping[category]:
                sec_text = extract_section(main_text, sec_name)
                if sec_text.strip():
                    parts.append(f"[섹션: {sec_name}]\n{sec_text}")
                    if verbose:
                        print(f"    섹션 '{sec_name}': {len(sec_text)}자")

        # 서브페이지 내용 추가
        for sub_name, sub_body in sub_texts.items():
            parts.append(f"[서브페이지: {sub_name}]\n{sub_body}")

        # 섹션 추출 실패했지만 매핑은 있는 경우 → 전체 본문 폴백
        if not parts and category in mapping:
            body_text = extract_body(main_text)
            if body_text.strip():
                parts.append(f"[본문 전체]\n{body_text[:5000]}")
                if verbose:
                    print(f"    ⚠️ 섹션 추출 실패 → 전체 본문 폴백 ({len(body_text)}자)")

        if not parts:
            if verbose:
                print(f"    ⚠️ 해당 섹션 없음 → 스킵")
            continue

        source_text = "\n\n".join(parts)
        if verbose:
            print(f"    총 {len(source_text)}자 → Gemini 분석 중...")

        lines = ask_gemini(movie_title, source_text, category)

        if lines:
            result[category] = lines
            if verbose:
                print(f"    ✅ {len(lines)}줄 추출")
        else:
            if verbose:
                print(f"    ⚠️ 관련 내용 없음")

    return result


# ============================================================
#  DB 저장
# ============================================================
def already_exists(cursor, movie_id: int, category: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM movie_tmi WHERE movie_id = %s AND category = %s LIMIT 1",
        (movie_id, category)
    )
    return cursor.fetchone() is not None


def run(overwrite: bool = False, target_title: str = None, dry_run: bool = False):
    conn   = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if target_title:
        cursor.execute("SELECT movie_id, title FROM movies WHERE title = %s", (target_title,))
    else:
        cursor.execute("SELECT movie_id, title FROM movies ORDER BY movie_id")

    movies = cursor.fetchall()
    print(f"대상 영화: {len(movies)}편\n")
    if dry_run:
        print("🔍 [DRY-RUN] 저장 없이 결과만 확인합니다.\n")

    insert_cursor = conn.cursor()
    total_saved   = 0
    total_skipped = 0
    total_failed  = 0

    for movie in movies:
        movie_id = movie["movie_id"]
        title    = movie["title"]
        print(f"\n{'='*50}")
        print(f"[{title}]")

        tmi_data = collect_tmi(title, verbose=True)

        if not tmi_data:
            print(f"  → TMI 수집 실패")
            total_failed += 1
            continue

        saved_this = 0
        try:
            for category, lines in tmi_data.items():
                if not overwrite and already_exists(insert_cursor, movie_id, category):
                    print(f"  [{category}] 이미 존재 → 스킵")
                    total_skipped += len(lines)
                    continue

                print(f"\n  [{category}] {len(lines)}줄 추출:")
                for i, line in enumerate(lines, 1):
                    print(f"    {i}. {line}")

                if dry_run:
                    continue

                if overwrite:
                    insert_cursor.execute(
                        "DELETE FROM movie_tmi WHERE movie_id = %s AND category = %s",
                        (movie_id, category)
                    )

                for content in lines:
                    insert_cursor.execute("""
                        INSERT INTO movie_tmi (movie_id, category, content, source_url)
                        VALUES (%s, %s, %s, %s)
                    """, (movie_id, category, content, "https://namu.wiki"))
                    saved_this += 1
                    total_saved += 1

                conn.commit()
                print(f"  [{category}] {len(lines)}건 저장")

        except Exception as e:
            conn.rollback()
            print(f"  ❌ DB 저장 오류: {e}")
            total_failed += 1
            continue

        if not dry_run:
            print(f"  → 총 {saved_this}건 저장 완료")
        time.sleep(0.5)

    insert_cursor.close()
    cursor.close()
    conn.close()

    print(f"\n{'='*50}")
    if dry_run:
        print(f"[DRY-RUN] 완료!  실패: {total_failed}편")
    else:
        print(f"완료!  저장: {total_saved}건 / 스킵: {total_skipped}건 / 실패: {total_failed}편")


# ============================================================
#  CLI
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini 2.5 Flash 기반 나무위키 TMI 크롤러")
    parser.add_argument("--overwrite", action="store_true", help="기존 데이터 덮어쓰기")
    parser.add_argument("--title",     type=str, default=None, help="특정 영화만 처리")
    parser.add_argument("--dry-run",   action="store_true",    help="저장 없이 결과 확인")
    args = parser.parse_args()

    run(overwrite=args.overwrite, target_title=args.title, dry_run=args.dry_run)
