import streamlit as st
import requests

API_BASE = "http://localhost:8000"
COLS = 5

st.set_page_config(page_title="영화 도슨트", page_icon="🎬", layout="wide")

st.markdown("""
<style>
    .poster-wrap {
        position: relative;
        width: 100%;
        padding-bottom: 150%;
        overflow: hidden;
        border-radius: 8px;
        background: #2a2a2a;
    }
    .poster-wrap img {
        position: absolute;
        top: 0; left: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
        border-radius: 8px;
    }
    .poster-title {
        font-size: 0.8em;
        text-align: center;
        color: #ddd;
        margin-top: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .review-card {
        background: #f8f8f8;
        border-left: 3px solid #E50914;
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 10px;
    }
    .chat-bubble-user {
        background: #DCF8C6;
        border-radius: 12px;
        padding: 10px 14px;
        margin: 6px 0;
        max-width: 75%;
        margin-left: auto;
        text-align: right;
    }
    .chat-bubble-bot {
        background: #F0F0F0;
        border-radius: 12px;
        padding: 10px 14px;
        margin: 6px 0;
        max-width: 75%;
    }
    .source-tag { font-size: 0.75em; color: #888; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

# URL 쿼리 파라미터로 페이지 상태 동기화 (브라우저 뒤로가기 지원)
params = st.query_params
if "movie_id" in params:
    st.session_state.page = "detail"
    st.session_state.selected_movie_id = int(params["movie_id"])
else:
    st.session_state.page = "home"
    st.session_state.selected_movie_id = None

for key, default in [("messages", [])]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── API 헬퍼 ──

@st.cache_data(ttl=300)
def fetch_movies():
    try:
        res = requests.get(f"{API_BASE}/movies", timeout=5)
        if res.status_code == 200:
            return res.json().get("movies", [])
    except Exception:
        pass
    return []


@st.cache_data(ttl=60)
def fetch_detail(movie_id: int):
    try:
        res = requests.get(f"{API_BASE}/movies/{movie_id}", timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


def send_chat(question: str, movie_title: str = None):
    payload = {"question": question}
    if movie_title:
        payload["movie_title"] = movie_title
    try:
        res = requests.post(f"{API_BASE}/chat", json=payload, timeout=15)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        return {"answer": f"API 연결 오류: {e}", "sources": "", "cached": False}
    return None


def do_grounding(movie_id: int, category: str):
    try:
        res = requests.post(
            f"{API_BASE}/grounding",
            json={"movie_id": movie_id, "category": category},
            timeout=30,
        )
        return res.json()
    except Exception as e:
        return {"message": f"오류: {e}", "saved": 0}


# ── 홈: 포스터 그리드 ──

def page_home():
    col_title, col_btn = st.columns([6, 1])
    col_title.markdown("## 🎬 영화 도슨트")
    col_title.caption("포스터를 클릭하면 상세 정보와 챗봇을 이용할 수 있어요")
    if col_btn.button("🔄 새로고침", use_container_width=True):
        fetch_movies.clear()
        fetch_detail.clear()
        st.rerun()

    movies = fetch_movies()
    if not movies:
        st.error("서버에 연결할 수 없어요. `uvicorn main:app --reload` 실행 후 새로고침하세요.")
        return

    for row_start in range(0, len(movies), COLS):
        row = movies[row_start:row_start + COLS]
        cols = st.columns(COLS)
        for col, movie in zip(cols, row):
            with col:
                img_src = movie.get("poster_url") or ""
                if img_src:
                    st.markdown(
                        f'<div class="poster-wrap"><img src="{img_src}"></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="poster-wrap" style="display:flex;align-items:center;'
                        'justify-content:center;color:#888;font-size:0.8em">포스터 없음</div>',
                        unsafe_allow_html=True,
                    )
                if st.button(movie["title"], key=f"m_{movie['movie_id']}", use_container_width=True):
                    st.query_params["movie_id"] = str(movie["movie_id"])
                    st.session_state.messages = []
                    st.rerun()


# ── 상세: 포스터 + 정보 + 탭 ──

def page_detail():
    movie_id = st.session_state.selected_movie_id
    detail = fetch_detail(movie_id)

    if st.button("← 목록으로"):
        st.query_params.clear()
        st.session_state.messages = []
        st.rerun()

    if not detail:
        st.error("영화 정보를 불러올 수 없어요.")
        return

    movie = detail.get("movie", {})

    # 포스터 + 기본 정보
    col_poster, col_info = st.columns([1, 3])

    with col_poster:
        if movie.get("poster_url"):
            st.image(movie["poster_url"], use_container_width=True)

    with col_info:
        st.markdown(f"## {movie.get('title', '')}")
        if movie.get("title_en"):
            st.caption(movie["title_en"])

        if movie.get("genre"):
            tags = "".join(
                f'<span style="background:#eee;border-radius:12px;padding:3px 10px;'
                f'margin-right:6px;font-size:0.9em">{g.strip()}</span>'
                for g in movie["genre"].split(",")
            )
            st.markdown(tags, unsafe_allow_html=True)
            st.markdown("")

        m1, m2 = st.columns(2)
        tmdb_r = movie.get("tmdb_rating")
        m1.metric("TMDB 평점", f"⭐ {tmdb_r} / 10" if tmdb_r else "-")
        m2.metric("관람등급", movie.get("age_rating") or "-")

        st.write(f"**개봉일**: {str(movie.get('release_date', '') or '')[:10] or '-'}")
        st.write(f"**감독**: {movie.get('director') or '정보 없음'}")
        if movie.get("cast_members"):
            st.write(f"**출연**: {movie['cast_members']}")
        if movie.get("overview"):
            st.info(movie["overview"])

        with st.expander("🔍 TMI 실시간 검색 (Gemini)"):
            cat = st.selectbox("카테고리", ["촬영지", "OST", "비하인드", "옥에티", "캐스팅비화"], key="grnd_cat")
            if st.button("검색 & 저장", key="grnd_btn"):
                with st.spinner("검색 중..."):
                    result = do_grounding(movie_id, cat)
                    fetch_detail.clear()
                st.success(f"{result.get('message', '')} ({result.get('saved', 0)}건 저장)")

    st.markdown("---")

    # 탭
    tab_review, tab_tmi, tab_chat = st.tabs(["📝 인기 리뷰 Top 10", "🎭 TMI", "💬 챗봇"])

    with tab_review:
        reviews = detail.get("top_reviews", [])
        if reviews:
            for r in reviews:
                rating_str = f"⭐ {r['rating']} / 5" if r.get("rating") else "별점 없음"
                st.markdown(f"""
                <div class="review-card">
                    <b>{r.get('reviewer_nickname', '익명')}</b> &nbsp; {rating_str} &nbsp; 👍 {r.get('likes_count', 0)}<br>
                    <span style="font-size:0.95em">{r.get('content', '')}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.write("리뷰가 없어요.")

    with tab_tmi:
        tmi_list = detail.get("tmi", [])
        if tmi_list:
            tmi_by_cat = {}
            for t in tmi_list:
                tmi_by_cat.setdefault(t.get("category", "기타"), []).append(t)
            for cat, items in tmi_by_cat.items():
                with st.expander(f"📌 {cat} ({len(items)}건)"):
                    for item in items:
                        st.write(item.get("content", ""))
                        if item.get("source_url"):
                            st.markdown(f"[출처]({item['source_url']})")
                        st.markdown("---")
        else:
            st.write("TMI 정보가 없어요. 위 '실시간 검색'을 눌러보세요!")

    with tab_chat:
        st.markdown(f"**{movie.get('title', '')}** 에 대해 무엇이든 물어보세요!")

        quick_cols = st.columns(4)
        for i, q in enumerate(["이 영화 볼만해?", "촬영지가 어디야?", "OST 어때?", "캐스팅 비화 알려줘"]):
            if quick_cols[i].button(q, key=f"q_{i}"):
                st.session_state.messages.append({"role": "user", "content": q, "sources": ""})
                result = send_chat(q, movie.get("title"))
                if result:
                    cached_label = " *(캐시)*" if result.get("cached") else ""
                    st.session_state.messages.append({
                        "role": "bot",
                        "content": result["answer"] + cached_label,
                        "sources": result.get("sources", ""),
                    })
                st.rerun()

        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-bubble-user">🧑 {msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-bubble-bot">🎬 {msg["content"]}</div>', unsafe_allow_html=True)
                if msg.get("sources"):
                    st.markdown(f'<div class="source-tag">📎 출처: {msg["sources"]}</div>', unsafe_allow_html=True)

        with st.form("chat_form", clear_on_submit=True):
            c1, c2 = st.columns([5, 1])
            user_input = c1.text_input("질문 입력", placeholder="예) 이 영화 무서워?", label_visibility="collapsed")
            submitted = c2.form_submit_button("전송 💬")

        if submitted and user_input.strip():
            question = user_input.strip()
            st.session_state.messages.append({"role": "user", "content": question, "sources": ""})
            with st.spinner("답변 생성 중..."):
                result = send_chat(question, movie.get("title"))
            if result:
                cached_label = " *(캐시)*" if result.get("cached") else ""
                st.session_state.messages.append({
                    "role": "bot",
                    "content": result["answer"] + cached_label,
                    "sources": result.get("sources", ""),
                })
            else:
                st.session_state.messages.append({"role": "bot", "content": "답변을 가져오지 못했어요.", "sources": ""})
            st.rerun()

        if st.button("🗑️ 대화 초기화", key="clear_chat"):
            st.session_state.messages = []
            st.rerun()


# ── 라우터 ──
if st.session_state.page == "home":
    page_home()
else:
    page_detail()
