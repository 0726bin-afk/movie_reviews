import os
import time
import warnings
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=FutureWarning)
import google.generativeai as genai

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


genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-2.5-flash")


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
#  0. 루트 → docs 리다이렉트
# ============================================================
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


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
            SELECT movie_id, title, genre, director, release_date, tmdb_rating, poster_url
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
#  5. 실시간 그라운딩 (Gemini + Google Search → DB 저장)
# ============================================================
CATEGORY_PROMPT = {
    "촬영지":     "영화 '{title}'의 실제 촬영 장소, 로케이션, 세트장에 대한 정보를 한국어로 요약해줘. TMI 형식으로 2~4문장씩 항목별로 정리해줘.",
    "OST":        "영화 '{title}'의 OST, 삽입곡, 음악에 대한 정보를 한국어로 요약해줘. TMI 형식으로 2~4문장씩 항목별로 정리해줘.",
    "비하인드":   "영화 '{title}'의 촬영 비하인드, 제작 뒷이야기, 에피소드를 한국어로 요약해줘. TMI 형식으로 2~4문장씩 항목별로 정리해줘.",
    "옥에티":     "영화 '{title}'의 옥에티, 고증 오류, 연속성 오류를 한국어로 요약해줘. TMI 형식으로 2~4문장씩 항목별로 정리해줘.",
    "캐스팅비화": "영화 '{title}'의 배우 캐스팅 과정, 오디션, 섭외 비화를 한국어로 요약해줘. TMI 형식으로 2~4문장씩 항목별로 정리해줘.",
}

@app.post("/grounding", tags=["그라운딩"])
def run_grounding(req: GroundingRequest):
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute("SELECT title FROM movies WHERE movie_id = %s", (req.movie_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="영화를 찾을 수 없어요.")
        title = row["title"]

        prompt_template = CATEGORY_PROMPT.get(req.category)
        if not prompt_template:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 카테고리: {req.category}")
        prompt = prompt_template.format(title=title)

        # Gemini + Google Search 그라운딩
        resp = gemini_model.generate_content(prompt)
        answer = resp.text.strip()

        source_url = "gemini-2.5-flash"

        # 줄 단위로 분리해서 저장
        lines = [l.strip() for l in answer.splitlines() if len(l.strip()) >= 20]
        saved = 0
        for line in lines:
            cursor.execute("""
                INSERT INTO movie_tmi (movie_id, category, content, source_url)
                VALUES (%s, %s, %s, %s)
            """, (req.movie_id, req.category, line, source_url))
            saved += 1

        conn.commit()
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
#  6. 챗봇 Q&A (캐시 → 메타데이터 답변 → RAG 연동 예정)
# ============================================================

def build_metadata_context(cursor, movie_title: str) -> str:
    """movies + movie_tmi 테이블에서 컨텍스트 문자열 생성"""
    cursor.execute("""
        SELECT title, title_en, genre, director, release_date,
               tmdb_rating, cast_members, overview, age_rating
        FROM movies WHERE title = %s
    """, (movie_title,))
    movie = cursor.fetchone()
    if not movie:
        return ""

    lines = [f"영화 제목: {movie['title']}"]
    if movie["title_en"]:
        lines.append(f"영문 제목: {movie['title_en']}")
    if movie["genre"]:
        lines.append(f"장르: {movie['genre']}")
    if movie["director"]:
        lines.append(f"감독: {movie['director']}")
    if movie["release_date"]:
        lines.append(f"개봉일: {str(movie['release_date'])[:10]}")
    if movie["tmdb_rating"]:
        lines.append(f"TMDB 평점: {movie['tmdb_rating']} / 10")
    if movie["age_rating"]:
        lines.append(f"관람등급: {movie['age_rating']}")
    if movie["cast_members"]:
        lines.append(f"출연진: {movie['cast_members']}")
    if movie["overview"]:
        lines.append(f"줄거리: {movie['overview']}")

    # TMI 추가
    cursor.execute("""
        SELECT category, content FROM movie_tmi
        WHERE movie_id = (SELECT movie_id FROM movies WHERE title = %s)
        ORDER BY category
    """, (movie_title,))
    tmi_rows = cursor.fetchall()
    if tmi_rows:
        lines.append("\n[TMI 정보]")
        for t in tmi_rows:
            lines.append(f"[{t['category']}] {t['content']}")

    return "\n".join(lines)


@app.post("/chat", tags=["챗봇"])
def chat(req: ChatRequest):
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cache_key = f"{req.movie_title or ''}||{req.question}"

        # 캐시 확인
        cursor.execute("""
            SELECT answer, sources FROM qa_log
            WHERE question = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (cache_key,))
        cached = cursor.fetchone()
        if cached:
            return {
                "question": req.question,
                "answer": cached["answer"],
                "sources": cached["sources"],
                "cached": True
            }

        # 메타데이터 기반 답변 (movie_title 있을 때)
        if req.movie_title:
            context = build_metadata_context(cursor, req.movie_title)
            if context:
                prompt = f"""당신은 영화 전문 도슨트입니다. 아래 영화 정보를 바탕으로 사용자 질문에 친절하고 자연스럽게 답변하세요.
정보에 없는 내용은 지어내지 말고 "해당 정보가 없어요"라고 답하세요.

[영화 정보]
{context}

[사용자 질문]
{req.question}"""
                resp = gemini_model.generate_content(prompt)
                answer = resp.text.strip()
                sources = "DB (영화 메타데이터 + TMI)"
            else:
                answer = f"'{req.movie_title}' 영화를 DB에서 찾을 수 없어요."
                sources = ""
        else:
            # TODO: RAG팀 파이프라인 연동 예정
            answer = "RAG 파이프라인 연동 대기 중입니다."
            sources = ""

        # QA 로그 저장
        cursor.execute("""
            INSERT INTO qa_log (question, answer, sources)
            VALUES (%s, %s, %s)
        """, (cache_key, answer, sources))
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