"""
youtube_tmi.py
==============
유튜브 영상 오디오 → Groq Whisper 전사 → Groq Llama TMI 추출 → Supabase 저장

흐름:
  1. "{title} 영화 {category}" 유튜브 검색
  2. 상위 영상 오디오 다운로드 (yt-dlp, 최대 20분)
  3. Groq Whisper로 한국어 전사
  4. Groq Llama로 카테고리별 TMI 추출
  5. DB 저장 후 오디오 파일 즉시 삭제

설치:
  pip install yt-dlp groq

실행:
  python youtube_tmi.py --title 라라랜드 --dry-run
  python youtube_tmi.py --title 파묘 --overwrite
  python youtube_tmi.py
"""

import os
import re
import time
import argparse
import tempfile
import glob
import psycopg2
import psycopg2.extras
import yt_dlp
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  DB / Groq 설정
# ============================================================
DB_CONFIG = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT", "5432"),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

groq_client   = Groq(api_key=os.getenv("GROQ_API_KEY"))
WHISPER_MODEL = "whisper-large-v3"
LLAMA_MODEL   = "llama-3.1-8b-instant"

ALL_CATEGORIES = ["촬영지", "OST", "비하인드", "옥에티", "캐스팅비화"]

CATEGORY_DESC = {
    "촬영지":     "영화를 촬영한 실제 장소, 로케이션, 세트장",
    "OST":        "영화 사운드트랙, 삽입곡, 음악",
    "비하인드":   "촬영 비하인드, 제작 뒷이야기, 에피소드",
    "옥에티":     "영화 속 고증 오류, 연속성 오류, 실수",
    "캐스팅비화": "배우 캐스팅 과정, 오디션, 섭외 비화",
}

YT_QUERIES = {
    "촬영지":     "{title} 영화 촬영지 로케이션",
    "OST":        "{title} 영화 OST 음악",
    "비하인드":   "{title} 영화 비하인드 제작 비화",
    "옥에티":     "{title} 영화 옥에티 오류",
    "캐스팅비화": "{title} 영화 캐스팅 비화 섭외",
}

MAX_VIDEOS_PER_CATEGORY = 1   # 카테고리당 영상 수
MAX_DURATION_SEC        = 1200  # 최대 20분


# ============================================================
#  유튜브 검색
# ============================================================
def search_youtube(query: str, max_results: int = 1) -> list[dict]:
    """유튜브 검색 → 영상 정보 목록 반환 (다운로드 없음)."""
    ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info    = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            entries = info.get("entries", []) or []
            # 20분 초과 영상 제외 (duration 없으면 통과)
            return [e for e in entries if (e.get("duration") or 0) <= MAX_DURATION_SEC]
    except Exception as e:
        print(f"    검색 오류: {e}")
        return []


# ============================================================
#  오디오 다운로드
# ============================================================
def download_audio(video_url: str, output_dir: str) -> tuple[str, str]:
    """
    오디오 다운로드. (파일경로, 영상URL) 반환.
    실패 시 ("", "") 반환.
    """
    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "format":      "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
        "outtmpl":     output_template,
        "quiet":       True,
        "no_warnings": True,
        "match_filter": yt_dlp.utils.match_filter_func(f"duration <= {MAX_DURATION_SEC}"),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info     = ydl.extract_info(video_url, download=True)
            video_id = info["id"]
            files    = glob.glob(os.path.join(output_dir, f"{video_id}.*"))
            if not files:
                return "", video_url
            return files[0], video_url
    except Exception as e:
        print(f"    다운로드 오류: {e}")
        return "", ""


# ============================================================
#  Groq Whisper 전사
# ============================================================
def transcribe(audio_path: str) -> str:
    """오디오 파일 → 한국어 텍스트."""
    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if size_mb > 25:
        print(f"    파일 크기 초과 ({size_mb:.1f}MB), 스킵")
        return ""

    for attempt in range(3):
        try:
            with open(audio_path, "rb") as f:
                result = groq_client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), f),
                    model=WHISPER_MODEL,
                    language="ko",
                    response_format="text",
                )
            return result if isinstance(result, str) else result.text
        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                match = re.search(r"(\d+(?:\.\d+)?)\s*s", err)
                wait  = float(match.group(1)) + 2 if match else 60
                print(f"    Whisper rate limit → {wait:.0f}초 대기...")
                time.sleep(wait)
            else:
                print(f"    Whisper 오류: {e}")
                return ""
    return ""


# ============================================================
#  Groq Llama TMI 추출
# ============================================================
def extract_tmi(title: str, category: str, transcript: str) -> list[str]:
    """전사 텍스트에서 카테고리 관련 TMI만 추출."""
    if not transcript.strip():
        return []

    prompt = f"""아래는 영화 '{title}'에 대한 유튜브 영상 자막입니다.
이 중에서 '{category}' 관련 TMI만 골라서 정리해줘.

'{category}'의 의미: {CATEGORY_DESC[category]}

규칙:
- 실제로 {category}에 해당하는 내용만 포함
- TMI 하나당 한 줄, 2~4문장으로 요약
- 관련 내용이 전혀 없으면 첫 줄에 "없음"이라고만 답해
- 번호나 기호 없이 줄글로

[영상 자막]
{transcript[:5000]}"""

    for attempt in range(3):
        try:
            resp   = groq_client.chat.completions.create(
                model=LLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=800,
            )
            result = resp.choices[0].message.content.strip()
            if result.startswith("없음"):
                return []
            return [l.strip() for l in result.splitlines() if len(l.strip()) >= 20]
        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                print(f"    Llama rate limit → 60초 대기...")
                time.sleep(60)
            else:
                print(f"    Llama 오류: {e}")
                return []
    return []


# ============================================================
#  DB 헬퍼
# ============================================================
def already_exists(cursor, movie_id: int, category: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM movie_tmi WHERE movie_id = %s AND category = %s LIMIT 1",
        (movie_id, category)
    )
    return cursor.fetchone() is not None


# ============================================================
#  메인
# ============================================================
def run(overwrite: bool = False, target_title: str = None, dry_run: bool = False):
    conn   = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if target_title:
        cursor.execute("SELECT movie_id, title FROM movies WHERE title = %s", (target_title,))
    else:
        cursor.execute("SELECT movie_id, title FROM movies ORDER BY movie_id")

    movies = cursor.fetchall()
    print(f"대상 영화: {len(movies)}편\n")

    insert_cursor = conn.cursor()
    total_saved   = 0
    total_skipped = 0

    for movie in movies:
        movie_id = movie["movie_id"]
        title    = movie["title"]
        print(f"\n{'='*50}")
        print(f"[{title}]")

        saved_this = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            for category in ALL_CATEGORIES:
                if not overwrite and already_exists(insert_cursor, movie_id, category):
                    print(f"  [{category}] 이미 존재 → 스킵")
                    total_skipped += 1
                    continue

                print(f"  [{category}] 유튜브 검색...")
                query  = YT_QUERIES[category].format(title=title)
                videos = search_youtube(query, max_results=MAX_VIDEOS_PER_CATEGORY)

                if not videos:
                    print(f"    검색 결과 없음")
                    continue

                all_lines = []

                for video in videos:
                    vid_url   = f"https://www.youtube.com/watch?v={video['id']}"
                    vid_title = video.get("title", "")
                    duration  = video.get("duration") or 0
                    print(f"    '{vid_title[:45]}' ({duration//60}분)")

                    # 오디오 다운로드
                    audio_path, src_url = download_audio(vid_url, tmpdir)
                    if not audio_path:
                        continue

                    # Whisper 전사
                    print(f"    전사 중...")
                    transcript = transcribe(audio_path)
                    os.remove(audio_path)  # 즉시 삭제

                    if not transcript:
                        continue
                    print(f"    전사 완료 ({len(transcript)}자)")

                    # TMI 추출
                    lines = extract_tmi(title, category, transcript)
                    if lines:
                        all_lines.extend([(line, src_url) for line in lines])

                    time.sleep(2)

                if not all_lines:
                    print(f"    관련 내용 없음, 스킵")
                    continue

                print(f"    → {len(all_lines)}줄 추출")

                if not dry_run:
                    if overwrite:
                        insert_cursor.execute(
                            "DELETE FROM movie_tmi WHERE movie_id = %s AND category = %s",
                            (movie_id, category)
                        )
                    for line, src_url in all_lines:
                        insert_cursor.execute("""
                            INSERT INTO movie_tmi (movie_id, category, content, source_url)
                            VALUES (%s, %s, %s, %s)
                        """, (movie_id, category, line, src_url))
                        saved_this += 1
                        total_saved += 1
                    conn.commit()
                    print(f"    → 저장 완료")

        print(f"  → 총 {saved_this}건 저장")
        time.sleep(1)

    insert_cursor.close()
    cursor.close()
    conn.close()

    print(f"\n{'='*50}")
    print(f"완료!  저장: {total_saved}건 / 스킵: {total_skipped}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="유튜브 + Groq Whisper TMI 수집기")
    parser.add_argument("--overwrite", action="store_true", help="기존 데이터 덮어쓰기")
    parser.add_argument("--title",     type=str, default=None, help="특정 영화만 처리")
    parser.add_argument("--dry-run",   action="store_true",    help="저장 없이 결과 확인")
    args = parser.parse_args()

    run(overwrite=args.overwrite, target_title=args.title, dry_run=args.dry_run)
