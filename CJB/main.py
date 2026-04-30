import os
import time
import warnings
import requests
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq

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

# Groq (채팅 답변용 — 무료)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
GROQ_MODEL  = "llama-3.3-70b-versatile"

# TMDB
TMDB_KEY  = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

# 이 키워드가 포함되면 TMDB 필모그래피 조회
TMDB_TRIGGER = ["다른 영화", "다른 작품", "전작", "필모그래피", "출연작", "감독 작품", "감독 영화"]

# 이 키워드가 포함되면 리뷰 기반 질문 (RAG 대상)
REVIEW_TRIGGER = [
    "볼만해", "재밌어", "재미있어", "추천", "호불호", "무서워", "지루해", "감동", "웃겨",
    "어때", "평가", "반응", "관객", "리뷰", "후기", "별로", "최고", "진짜", "실망",
    "어떤 영화", "어떤가", "어떤지", "좋아", "싫어", "괜찮아",
    "단점", "장점", "아쉬운", "아쉬워", "문제", "약점", "나쁜", "좋은 점", "별점",
    "worth", "재미", "몰입", "스토리", "연기", "결말", "반전", "ost", "음악",
    "강점", "취약", "부족", "완성도", "퀄리티", "수작", "졸작", "명작"
]


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
#  6. 챗봇 헬퍼
# ============================================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

def fetch_serpapi_context(movie_title: str, question: str) -> str:
    """SerpAPI로 '{영화제목} {질문}' 구글 검색 → 상위 스니펫 반환"""
    try:
        from serpapi import GoogleSearch
        search = GoogleSearch({
            "q": f"{movie_title} {question}",
            "api_key": SERPAPI_KEY,
            "hl": "ko",
            "gl": "kr",
            "num": 5,
        })
        results = search.get_dict()
        snippets = []
        for r in results.get("organic_results", [])[:5]:
            title   = r.get("title", "")
            snippet = r.get("snippet", "")
            if snippet:
                snippets.append(f"- {title}: {snippet}")
        return "\n".join(snippets)
    except Exception:
        return ""


def ask_groq(prompt: str) -> str:
    resp = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 한국어 영화 전문 도슨트입니다. "
                    "반드시 순수한 한국어로만 답변하세요. "
                    "한자(漢字), 중국어 간체/번체, 일본어 히라가나/가타카나를 절대 사용하지 마세요. "
                    "컨텍스트에 한자가 포함되어 있어도 반드시 한글로 바꿔서 답변하세요. "
                    "예: '欠' → '부족', '缺' → '결함', '点' → '점' 으로 변환."
                )
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1024,
    )
    return resp.choices[0].message.content.strip()


def tmdb_get(path: str, **params) -> dict:
    res = requests.get(
        f"{TMDB_BASE}/{path}",
        params={"api_key": TMDB_KEY, "language": "ko-KR", **params},
        timeout=10,
    )
    return res.json()


def fetch_director_filmography(tmdb_id: int) -> tuple:
    """감독 필모그래피 — (이름, 영화 목록)"""
    credits = tmdb_get(f"movie/{tmdb_id}/credits")
    director = next((c for c in credits.get("crew", []) if c.get("job") == "Director"), None)
    if not director:
        return "", []
    person_id = director["id"]
    name = director["name"]
    data = tmdb_get(f"person/{person_id}/movie_credits")
    films = sorted(
        [m for m in data.get("crew", [])
         if m.get("job") == "Director" and m.get("title") and m.get("release_date")],
        key=lambda x: x.get("release_date", ""), reverse=True
    )[:10]
    return name, films


def fetch_actor_filmography(tmdb_id: int, actor_name: str = None) -> tuple:
    """배우 필모그래피 — (이름, 영화 목록). actor_name 지정 시 해당 배우 우선"""
    credits = tmdb_get(f"movie/{tmdb_id}/credits")
    cast = credits.get("cast", [])
    if actor_name:
        person = next((c for c in cast if actor_name in c.get("name", "")), None) or (cast[0] if cast else None)
    else:
        person = cast[0] if cast else None
    if not person:
        return "", []
    person_id = person["id"]
    name = person["name"]
    data = tmdb_get(f"person/{person_id}/movie_credits")
    films = sorted(
        [m for m in data.get("cast", []) if m.get("title") and m.get("release_date")],
        key=lambda x: x.get("release_date", ""), reverse=True
    )[:10]
    return name, films


def fetch_tmdb_extra(tmdb_id: int) -> list:
    """TMDB에서 OTT·흥행·키워드·유사영화 조회 → 컨텍스트 라인 리스트 반환"""
    lines = []
    try:
        # 상세 정보 (흥행 수익·제작비·런타임·태그라인)
        detail = tmdb_get(f"movie/{tmdb_id}")
        if detail.get("runtime"):
            lines.append(f"러닝타임: {detail['runtime']}분")
        if detail.get("tagline"):
            lines.append(f"태그라인: {detail['tagline']}")
        if detail.get("revenue"):
            lines.append(f"전세계 흥행 수익: ${detail['revenue']:,}")
        if detail.get("budget"):
            lines.append(f"제작비: ${detail['budget']:,}")
        if detail.get("vote_count"):
            lines.append(f"TMDB 평가 수: {detail['vote_count']:,}명")
        if detail.get("popularity"):
            lines.append(f"TMDB 인기도: {detail['popularity']:.1f}")
        prod = [c["name"] for c in detail.get("production_countries", [])]
        if prod:
            lines.append(f"제작 국가: {', '.join(prod)}")
        orig_lang = detail.get("original_language")
        if orig_lang:
            lines.append(f"원본 언어: {orig_lang}")

        # 한국 OTT 서비스
        providers = tmdb_get(f"movie/{tmdb_id}/watch/providers")
        kr = providers.get("results", {}).get("KR", {})
        if kr:
            streaming = [p["provider_name"] for p in kr.get("flatrate", [])]
            rental    = [p["provider_name"] for p in kr.get("rent", [])]
            buy       = [p["provider_name"] for p in kr.get("buy", [])]
            if streaming:
                lines.append(f"한국 스트리밍 (구독): {', '.join(streaming)}")
            if rental:
                lines.append(f"한국 스트리밍 (대여): {', '.join(rental)}")
            if buy:
                lines.append(f"한국 스트리밍 (구매): {', '.join(buy)}")
            if not streaming and not rental and not buy:
                lines.append("한국 OTT: 현재 등록된 스트리밍 서비스 없음")
        else:
            lines.append("한국 OTT: 정보 없음")

        # 키워드
        kw_data = tmdb_get(f"movie/{tmdb_id}/keywords")
        kw_list = [k["name"] for k in kw_data.get("keywords", [])[:15]]
        if kw_list:
            lines.append(f"관련 키워드: {', '.join(kw_list)}")

        # 유사 영화 추천
        similar = tmdb_get(f"movie/{tmdb_id}/similar")
        sim_titles = [m["title"] for m in similar.get("results", [])[:5] if m.get("title")]
        if sim_titles:
            lines.append(f"비슷한 영화 (TMDB 추천): {', '.join(sim_titles)}")

    except Exception:
        pass  # TMDB 일부 실패해도 나머지 컨텍스트로 답변

    return lines


def fetch_reviews_context(cursor, movie_title: str, limit: int = 20) -> str:
    """DB 리뷰를 직접 가져와 컨텍스트 생성 (RAG 대체 임시 처리)"""
    cursor.execute("""
        SELECT r.rating, r.content, r.likes_count
        FROM reviews r
        JOIN movies m ON r.movie_id = m.movie_id
        WHERE m.title = %s AND r.content IS NOT NULL AND LENGTH(r.content) > 10
        ORDER BY r.likes_count DESC
        LIMIT %s
    """, (movie_title, limit))
    rows = cursor.fetchall()
    if not rows:
        return ""
    lines = [f"[리뷰 {i+1}] 평점 {r['rating']} — {r['content']}" for i, r in enumerate(rows)]
    return "\n".join(lines)


def build_metadata_context(cursor, movie_title: str) -> str:
    """movies + movie_tmi + TMDB 전체 컨텍스트 문자열 생성"""
    cursor.execute("""
        SELECT title, title_en, genre, director, release_date,
               tmdb_rating, cast_members, overview, age_rating, tmdb_id
        FROM movies WHERE title = %s
    """, (movie_title,))
    movie = cursor.fetchone()
    if not movie:
        return ""

    lines = [f"영화 제목: {movie['title']}"]
    if movie["title_en"]:     lines.append(f"영문 제목: {movie['title_en']}")
    if movie["genre"]:        lines.append(f"장르: {movie['genre']}")
    if movie["director"]:     lines.append(f"감독: {movie['director']}")
    if movie["release_date"]: lines.append(f"개봉일: {str(movie['release_date'])[:10]}")
    if movie["tmdb_rating"]:  lines.append(f"TMDB 평점: {movie['tmdb_rating']} / 10")
    if movie["age_rating"]:   lines.append(f"관람등급: {movie['age_rating']}")
    if movie["cast_members"]: lines.append(f"출연진: {movie['cast_members']}")
    if movie["overview"]:     lines.append(f"줄거리: {movie['overview']}")

    # TMDB 추가 정보 (OTT·흥행·키워드·유사영화)
    if movie["tmdb_id"]:
        extra = fetch_tmdb_extra(movie["tmdb_id"])
        if extra:
            lines.append("\n[TMDB 추가 정보]")
            lines.extend(extra)

    # TMI
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


# ============================================================
#  7. 챗봇 Q&A
# ============================================================
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
            return {"question": req.question, "answer": cached["answer"],
                    "sources": cached["sources"], "cached": True}

        answer = ""
        sources = ""

        if req.movie_title:
            # 질문 유형 분류
            needs_tmdb   = any(k in req.question for k in TMDB_TRIGGER)
            needs_review = any(k in req.question for k in REVIEW_TRIGGER)

            # ── 리뷰 기반 질문 (RAG 대상) ──────────────────────────
            # TODO: RAG팀 파이프라인 완성 후 아래 블록을 RAG 호출로 교체
            if needs_review and not needs_tmdb:
                review_context = fetch_reviews_context(cursor, req.movie_title)
                if review_context:
                    prompt = f"""당신은 영화 전문 도슨트입니다. 아래 실제 관객 리뷰를 분석해서 사용자 질문에 친절하게 한국어로 답변하세요.
리뷰에 없는 내용은 지어내지 말고 리뷰 데이터 기반으로만 답변하세요.

[영화: {req.movie_title} 관객 리뷰 (좋아요 순 상위 20개)]
{review_context}

[사용자 질문]
{req.question}"""
                    answer = ask_groq(prompt)
                    sources = "DB 리뷰 (RAG 예정)"

                    cursor.execute("""
                        INSERT INTO qa_log (question, answer, sources)
                        VALUES (%s, %s, %s)
                    """, (cache_key, answer, sources))
                    conn.commit()
                    return {"question": req.question, "answer": answer,
                            "sources": sources, "cached": False}

            # ── TMDB 필모그래피 질문 ──────────────────────────────
            if needs_tmdb:
                cursor.execute("SELECT tmdb_id FROM movies WHERE title = %s", (req.movie_title,))
                row = cursor.fetchone()
                tmdb_id = row["tmdb_id"] if row else None

                if tmdb_id:
                    is_director_q = any(k in req.question for k in ["감독", "전작", "필모그래피"])
                    if is_director_q:
                        person_name, films = fetch_director_filmography(tmdb_id)
                        role = "감독"
                    else:
                        person_name, films = fetch_actor_filmography(tmdb_id)
                        role = "배우"

                    if films:
                        film_list = "\n".join(
                            f"- {m['title']} ({m.get('release_date','')[:4]})"
                            for m in films
                        )
                        prompt = f"""당신은 영화 전문 도슨트입니다. 아래 TMDB 데이터를 바탕으로 사용자 질문에 친절하게 한국어로 답변하세요.

[{person_name} {role} 필모그래피 (TMDB 기준, 최신순)]
{film_list}

[사용자 질문]
{req.question}"""
                        answer = ask_groq(prompt)
                        sources = f"TMDB ({person_name} 필모그래피)"

            # TMDB 조회 실패 또는 일반 메타데이터 질문
            if not answer:
                context = build_metadata_context(cursor, req.movie_title)
                if context:
                    # SerpAPI 실시간 검색 보조 컨텍스트
                    web_context = fetch_serpapi_context(req.movie_title, req.question)
                    web_section = f"\n[웹 검색 결과]\n{web_context}" if web_context else ""

                    prompt = f"""당신은 영화 전문 도슨트입니다. 아래 영화 정보와 웹 검색 결과를 바탕으로 사용자 질문에 친절하고 자연스럽게 한국어로 답변하세요.
확실하지 않은 내용은 지어내지 말고 "확인이 필요해요"라고 답하세요.

[영화 정보]
{context}
{web_section}

[사용자 질문]
{req.question}"""
                    answer = ask_groq(prompt)
                    sources = "DB + TMDB + 웹 검색"
                else:
                    answer = f"'{req.movie_title}' 영화를 DB에서 찾을 수 없어요."
        else:
            # TODO: RAG팀 파이프라인 연동 예정
            answer = "RAG 파이프라인 연동 대기 중입니다."

        # QA 로그 저장
        cursor.execute("""
            INSERT INTO qa_log (question, answer, sources)
            VALUES (%s, %s, %s)
        """, (cache_key, answer, sources))
        conn.commit()

        return {"question": req.question, "answer": answer,
                "sources": sources, "cached": False}
    finally:
        cursor.close()
        conn.close()