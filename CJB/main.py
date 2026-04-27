import os
import time
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from ddgs import DDGS

load_dotenv()

# ============================================================
#  앱 설정
# ============================================================
app = FastAPI(
    title="영화 도슨트 챗봇 API",
    description="리뷰 기반 영화 가이드 챗봇 서비스",
    version="1.0.0"
)

# ============================================================
#  DB 연결
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
#  요청/응답 모델
# ============================================================
class ChatRequest(BaseModel):
    question: str
    movie_title: str | None = None  # 특정 영화 지정 시 사용

class GroundingRequest(BaseModel):
    movie_id: int
    category: str   # 촬영지 / OST / 비하인드 / 옥에티 / 캐스팅비화


# ============================================================
#  1. 헬스 체크
# ============================================================
@app.get("/health", tags=["서버"])
def health_check():
    return {"status": "ok", "message": "서버 정상 작동 중"}


# ============================================================
#  2. 영화 목록 조회
# ============================================================
@app.get("/movies", tags=["영화"])
def get_movies():
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("""
            SELECT movie_id, title, genre, director, release_date, tmdb_rating
            FROM movies
            ORDER BY movie_id
        """)
        movies = cursor.fetchall()
        return {"count": len(movies), "movies": movies}
    finally:
        cursor.close()
        conn.close()


# ============================================================
#  3. 영화 상세 조회 (리뷰 + TMI 포함)
# ============================================================
@app.get("/movies/{movie_id}", tags=["영화"])
def get_movie_detail(movie_id: int):
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # 영화 기본 정보
        cursor.execute("SELECT * FROM movies WHERE movie_id = %s", (movie_id,))
        movie = cursor.fetchone()
        if not movie:
            raise HTTPException(status_code=404, detail="영화를 찾을 수 없어요.")

        # 리뷰 상위 10개
        cursor.execute("""
            SELECT reviewer_nickname, rating, likes_count, content
            FROM reviews
            WHERE movie_id = %s
            ORDER BY likes_count DESC
            LIMIT 10
        """, (movie_id,))
        reviews = cursor.fetchall()

        # TMI 목록
        cursor.execute("""
            SELECT category, content, source_url
            FROM movie_tmi
            WHERE movie_id = %s
            ORDER BY category
        """, (movie_id,))
        tmi = cursor.fetchall()

        return {
            "movie": movie,
            "top_reviews": reviews,
            "tmi": tmi
        }
    finally:
        cursor.close()
        conn.close()


# ============================================================
#  4. TMI 조회
# ============================================================
@app.get("/tmi/{movie_id}", tags=["TMI"])
def get_tmi(movie_id: int, category: str | None = None):
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if category:
            cursor.execute("""
                SELECT category, content, source_url, created_at
                FROM movie_tmi
                WHERE movie_id = %s AND category = %s
            """, (movie_id, category))
        else:
            cursor.execute("""
                SELECT category, content, source_url, created_at
                FROM movie_tmi
                WHERE movie_id = %s
                ORDER BY category
            """, (movie_id,))
        tmi = cursor.fetchall()
        return {"movie_id": movie_id, "count": len(tmi), "tmi": tmi}
    finally:
        cursor.close()
        conn.close()


# ============================================================
#  5. 실시간 그라운딩 (DuckDuckGo 검색 → DB 저장)
# ============================================================
TMI_QUERY_TEMPLATES = {
    "촬영지":     "{title} 영화 촬영지",
    "OST":        "{title} 영화 OST 음악",
    "비하인드":   "{title} 영화 제작 비하인드 비화",
    "옥에티":     "{title} 영화 옥에티 실수",
    "캐스팅비화": "{title} 영화 캐스팅 비화",
}

@app.post("/grounding", tags=["그라운딩"])
def run_grounding(req: GroundingRequest):
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # 영화 제목 조회
        cursor.execute("SELECT title FROM movies WHERE movie_id = %s", (req.movie_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="영화를 찾을 수 없어요.")
        title = row["title"]

        # 검색어 생성
        template = TMI_QUERY_TEMPLATES.get(req.category)
        if not template:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 카테고리: {req.category}")
        query = template.format(title=title)

        # DuckDuckGo 검색
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="kr-kr", max_results=3))

        saved = 0
        for result in results:
            content    = result.get("body", "").strip()
            source_url = result.get("href", "")
            if not content:
                continue
            cursor.execute("""
                INSERT INTO movie_tmi (movie_id, category, content, source_url)
                VALUES (%s, %s, %s, %s)
            """, (req.movie_id, req.category, content, source_url))
            saved += 1

        conn.commit()
        time.sleep(1)
        return {"message": f"'{req.category}' 그라운딩 완료", "saved": saved}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# ============================================================
#  6. 챗봇 Q&A (캐시 확인 → RAG 연동 예정)
# ============================================================
@app.post("/chat", tags=["챗봇"])
def chat(req: ChatRequest):
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # 캐시 확인 (동일 질문 있으면 바로 반환)
        cursor.execute("""
            SELECT answer, sources FROM qa_log
            WHERE question = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (req.question,))
        cached = cursor.fetchone()
        if cached:
            return {
                "question": req.question,
                "answer": cached["answer"],
                "sources": cached["sources"],
                "cached": True
            }

        # TODO: RAG팀 파이프라인 연동 예정
        # answer = rag_pipeline.query(req.question)
        answer  = "RAG 파이프라인 연동 대기 중입니다."
        sources = ""

        # QA 로그 저장
        cursor.execute("""
            INSERT INTO qa_log (question, answer, sources)
            VALUES (%s, %s, %s)
        """, (req.question, answer, sources))
        conn.commit()

        return {
            "question": req.question,
            "answer": answer,
            "sources": sources,
            "cached": False
        }
    finally:
        cursor.close()
        conn.close()