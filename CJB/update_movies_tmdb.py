import os
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  연결 설정
# ============================================================
DB_CONFIG = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT", "5432"),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_DETAIL_URL = "https://api.themoviedb.org/3/movie/{movie_id}"


def search_tmdb(title):
    """영화 제목으로 TMDB 검색 → 첫 번째 결과 반환"""
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "ko-KR",   # 한국어 결과 우선
    }
    res = requests.get(TMDB_SEARCH_URL, params=params)
    results = res.json().get("results", [])

    if not results:
        print(f"  [TMDB] '{title}' 검색 결과 없음")
        return None

    return results[0]  # 첫 번째 결과 사용


def get_tmdb_detail(tmdb_id):
    """TMDB ID로 상세 정보(감독 등) 조회"""
    url = TMDB_DETAIL_URL.format(movie_id=tmdb_id)
    params = {
        "api_key": TMDB_API_KEY,
        "language": "ko-KR",
        "append_to_response": "credits",  # 감독/배우 정보 포함
    }
    res = requests.get(url, params=params)
    return res.json()


def extract_director(credits):
    """credits에서 감독 이름 추출"""
    crew = credits.get("crew", [])
    directors = [p["name"] for p in crew if p.get("job") == "Director"]
    return ", ".join(directors) if directors else None


def extract_genre(genres):
    """장르 리스트 → 문자열로 변환 (예: '액션, 공포')"""
    return ", ".join([g["name"] for g in genres]) if genres else None


def update_movies():
    """movies 테이블의 모든 영화를 TMDB 데이터로 업데이트"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 메타데이터가 아직 없는 영화만 조회 (tmdb_id가 NULL인 것)
    cursor.execute("SELECT movie_id, title FROM movies WHERE tmdb_id IS NULL")
    movies = cursor.fetchall()

    if not movies:
        print("업데이트할 영화가 없어요. (이미 모두 완료됨)")
        conn.close()
        return

    print(f"\n총 {len(movies)}개 영화 메타데이터 업데이트 시작...\n")

    success = 0
    failed = 0

    for movie_id, title in movies:
        print(f"[{title}] 처리 중...")

        # 1. TMDB 검색
        result = search_tmdb(title)
        if not result:
            failed += 1
            continue

        tmdb_id = result["id"]

        # 2. 상세 정보 조회 (감독 포함)
        detail = get_tmdb_detail(tmdb_id)

        director   = extract_director(detail.get("credits", {}))
        genre      = extract_genre(detail.get("genres", []))
        release    = detail.get("release_date") or None      # 빈 문자열 → None
        tmdb_rating = detail.get("vote_average") or None

        # 3. DB 업데이트
        cursor.execute("""
            UPDATE movies
            SET
                tmdb_id      = %s,
                genre        = %s,
                director     = %s,
                release_date = %s,
                tmdb_rating  = %s
            WHERE movie_id = %s
        """, (tmdb_id, genre, director, release, tmdb_rating, movie_id))

        conn.commit()
        success += 1
        print(f"  ✅ tmdb_id={tmdb_id} | 장르={genre} | 감독={director} | 개봉={release} | 평점={tmdb_rating}")

    print(f"\n완료! 성공: {success}개 / 실패: {failed}개")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    update_movies()