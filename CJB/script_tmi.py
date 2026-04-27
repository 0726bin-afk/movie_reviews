"""
script_tmi.py
=============
scripts/ 폴더의 {영화제목}_*.txt → Gemini 2.5 Flash로 카테고리별 TMI 추출 → Supabase 저장

실행:
  python script_tmi.py --title 살인의추억       # 특정 영화
  python script_tmi.py                          # scripts/ 폴더 전체 처리
  python script_tmi.py --title 살인의추억 --overwrite
  python script_tmi.py --title 살인의추억 --dry-run
"""

import os
import time
import warnings
import argparse
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=FutureWarning)
import google.generativeai as genai

load_dotenv()

# ============================================================
#  설정
# ============================================================
DB_CONFIG = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT", "5432"),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model  = genai.GenerativeModel("gemini-2.5-flash")
API_CALL_INTERVAL = 4  # 분당 15회 제한 → 4초 간격

SCRIPTS_DIR = Path(__file__).parent / "scripts"

ALL_CATEGORIES = ["촬영지", "OST", "비하인드", "옥에티", "캐스팅비화"]

CATEGORY_DESC = {
    "촬영지":     "영화를 촬영한 실제 장소, 로케이션, 세트장",
    "OST":        "영화 사운드트랙, 삽입곡, 음악",
    "비하인드":   "촬영 비하인드, 제작 뒷이야기, 에피소드",
    "옥에티":     "영화 속 고증 오류, 연속성 오류, 실수",
    "캐스팅비화": "배우 캐스팅 과정, 오디션, 섭외 비화",
}


# ============================================================
#  Gemini 추출
# ============================================================
def ask_gemini(title: str, category: str, text: str) -> list[str]:
    """스크립트 텍스트에서 카테고리 관련 TMI만 추출."""

    prompt = f"""아래는 영화 '{title}'에 대한 스크립트/기사입니다.
이 중에서 '{category}' 관련 TMI만 골라서 정리해줘.

'{category}'의 의미: {CATEGORY_DESC[category]}

규칙:
- 스크립트가 영어여도 반드시 한국어로 작성
- 실제로 {category}에 해당하는 내용만 포함
- '이 장면' 같은 지시어가 나오면 앞뒤 문맥으로 어떤 장면인지 유추해서 구체적으로 써줘
- TMI 하나당 한 줄, 2~4문장으로 요약
- 관련 내용이 전혀 없으면 첫 줄에 "없음"이라고만 답해
- 번호나 기호 없이 줄글로

[스크립트]
{text[:8000]}"""

    for attempt in range(3):
        try:
            resp   = gemini_model.generate_content(prompt)
            result = resp.text.strip()
            time.sleep(API_CALL_INTERVAL)
            if result.startswith("없음"):
                return []
            return [l.strip() for l in result.splitlines() if len(l.strip()) >= 20]

        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                if "day" in err.lower() or "daily" in err.lower():
                    print(f"    ❌ 일일 한도 초과.")
                    return []
                print(f"    rate limit → 60초 대기 (attempt {attempt+1}/3)...")
                time.sleep(60)
            else:
                print(f"    Gemini 오류: {e}")
                return []

    return []


# ============================================================
#  DB 헬퍼
# ============================================================
def get_movie_id(cursor, title: str) -> int | None:
    cursor.execute("SELECT movie_id FROM movies WHERE title = %s", (title,))
    row = cursor.fetchone()
    return row["movie_id"] if row else None


def already_exists(cursor, movie_id: int, category: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM movie_tmi WHERE movie_id = %s AND category = %s LIMIT 1",
        (movie_id, category)
    )
    return cursor.fetchone() is not None


# ============================================================
#  메인
# ============================================================
def process(title: str, overwrite: bool, dry_run: bool,
            conn, cursor, insert_cursor) -> int:
    """영화 하나 처리. 저장 건수 반환."""

    txt_files = sorted(SCRIPTS_DIR.glob(f"{title}_*.txt"))
    if not txt_files:
        print(f"  ❌ 파일 없음: {SCRIPTS_DIR / title}_*.txt")
        return 0

    movie_id = get_movie_id(cursor, title)
    if not movie_id:
        print(f"  ❌ DB에 '{title}' 없음 (insert_movies.py 먼저 실행)")
        return 0

    parts = []
    for p in txt_files:
        content = p.read_text(encoding="utf-8")
        parts.append(f"[출처: {p.name}]\n{content}")
        print(f"  {p.name} {len(content)}자 로드")
    text = "\n\n" + "="*40 + "\n\n".join(parts)
    source_names = ";".join(p.name for p in txt_files)
    print(f"  총 {len(text)}자")

    saved_this = 0
    for category in ALL_CATEGORIES:
        if not overwrite and already_exists(insert_cursor, movie_id, category):
            print(f"  [{category}] 이미 존재 → 스킵")
            continue

        print(f"  [{category}] Gemini 분석 중...")
        lines = ask_gemini(title, category, text)

        if not lines:
            print(f"    → 관련 내용 없음, 스킵")
            continue

        print(f"    → {len(lines)}줄 추출")

        if not dry_run:
            if overwrite:
                insert_cursor.execute(
                    "DELETE FROM movie_tmi WHERE movie_id = %s AND category = %s",
                    (movie_id, category)
                )
            for line in lines:
                insert_cursor.execute("""
                    INSERT INTO movie_tmi (movie_id, category, content, source_url)
                    VALUES (%s, %s, %s, %s)
                """, (movie_id, category, line, source_names))
                saved_this += 1
            conn.commit()
            print(f"    → 저장 완료")

    return saved_this


def run(overwrite: bool = False, target_title: str = None, dry_run: bool = False):
    conn   = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    insert_cursor = conn.cursor()

    if target_title:
        titles = [target_title]
    else:
        titles = sorted({
            "_".join(f.stem.split("_")[:-1])
            for f in SCRIPTS_DIR.glob("*_*.txt")
        })

    print(f"처리할 영화: {titles}\n")

    total_saved = 0
    for title in titles:
        print(f"\n{'='*50}")
        print(f"[{title}]")
        saved = process(title, overwrite, dry_run, conn, cursor, insert_cursor)
        total_saved += saved
        print(f"  → {saved}건 저장")

    insert_cursor.close()
    cursor.close()
    conn.close()

    print(f"\n{'='*50}")
    print(f"완료!  총 저장: {total_saved}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="스크립트 txt → Gemini TMI 추출기")
    parser.add_argument("--title",     type=str, default=None, help="특정 영화 제목")
    parser.add_argument("--overwrite", action="store_true",    help="기존 데이터 덮어쓰기")
    parser.add_argument("--dry-run",   action="store_true",    help="저장 없이 결과 확인")
    args = parser.parse_args()

    run(overwrite=args.overwrite, target_title=args.title, dry_run=args.dry_run)
