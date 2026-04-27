"""
fetch_web.py
============
웹 페이지 또는 유튜브 URL → 텍스트 추출 → {영화제목}_웹.txt 저장
영문 페이지도 그대로 저장 (script_tmi.py가 한국어로 번역해서 TMI 추출)

실행:
  python fetch_web.py --url "https://en.wikipedia.org/wiki/The_Godfather" --title 대부
  python fetch_web.py --url "https://www.imdb.com/title/tt0068646/trivia/" --title 대부
  python fetch_web.py --url "https://www.youtube.com/watch?v=xxxx" --title 대부
  python fetch_web.py --url "https://..." --title 대부 --append   # 기존 파일에 이어서 추가
"""

import os
import re
import argparse
import requests
from bs4 import BeautifulSoup
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent / "scripts"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def extract_video_id(url: str) -> str | None:
    for pattern in [r"v=([A-Za-z0-9_-]{11})", r"youtu\.be/([A-Za-z0-9_-]{11})"]:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_youtube(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=["en", "en-US", "ko", "ko-KR"])
    except Exception as e:
        print(f"  ⚠️ 한/영 자막 없음 ({e}), 폴백 시도...")
        try:
            tlist = api.list(video_id)
            langs = [t.language_code for t in tlist]
            fetched = api.fetch(video_id, languages=langs)
        except Exception as e2:
            print(f"  ❌ 자막 오류: {e2}")
            return ""
    lines = [entry.text.strip().replace("\n", " ") for entry in fetched if entry.text.strip()]
    return "\n".join(lines)


def fetch_webpage(url: str) -> str:
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
            tag.decompose()
        lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if len(l.strip()) > 20]
        return "\n".join(lines)
    except Exception as e:
        print(f"  ❌ 웹 페이지 오류: {e}")
        return ""


def save_text(title: str, text: str, suffix: str, append: bool) -> str:
    SCRIPTS_DIR.mkdir(exist_ok=True)
    filepath = SCRIPTS_DIR / f"{title}_{suffix}.txt"
    mode = "a" if (append and filepath.exists()) else "w"
    with open(filepath, mode, encoding="utf-8") as f:
        if mode == "a":
            f.write("\n\n" + "=" * 50 + "\n\n")
        f.write(text)
    return str(filepath)


def run(url: str, title: str, append: bool = False):
    video_id = extract_video_id(url)
    if video_id:
        print(f"유튜브 감지 (id: {video_id}), 자막 추출 중...")
        text   = fetch_youtube(video_id)
        suffix = "유튜브"
    else:
        print(f"웹 페이지 fetch 중: {url}")
        text   = fetch_webpage(url)
        suffix = "웹"

    if not text:
        print("텍스트를 가져오지 못했습니다.")
        return

    print(f"  {len(text.splitlines())}줄 추출 완료")
    filepath = save_text(title, text, suffix, append)
    print(f"저장 완료: {filepath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="웹/유튜브 텍스트 추출기")
    parser.add_argument("--url",    required=True,      help="URL (웹 페이지 또는 유튜브)")
    parser.add_argument("--title",  required=True,      help="영화 제목")
    parser.add_argument("--append", action="store_true", help="기존 파일에 이어서 추가")
    args = parser.parse_args()
    run(url=args.url, title=args.title, append=args.append)
