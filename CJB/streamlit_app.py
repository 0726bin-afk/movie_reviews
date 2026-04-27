import streamlit as st
import requests

# ============================================================
#  설정
# ============================================================
API_BASE = "http://localhost:8000"   # FastAPI 서버 주소

st.set_page_config(
    page_title="영화 도슨트 챗봇",
    page_icon="🎬",
    layout="wide",
)

# ============================================================
#  CSS 스타일
# ============================================================
st.markdown("""
<style>
    .chat-bubble-user {
        background-color: #DCF8C6;
        border-radius: 12px;
        padding: 10px 14px;
        margin: 6px 0;
        max-width: 75%;
        margin-left: auto;
        text-align: right;
    }
    .chat-bubble-bot {
        background-color: #F0F0F0;
        border-radius: 12px;
        padding: 10px 14px;
        margin: 6px 0;
        max-width: 75%;
    }
    .source-tag {
        font-size: 0.75em;
        color: #888;
        margin-top: 4px;
    }
    .movie-card {
        background: #FAFAFA;
        border: 1px solid #E0E0E0;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
#  헬퍼 함수
# ============================================================
@st.cache_data(ttl=60)
def fetch_movies():
    """영화 목록 가져오기 (1분 캐시)"""
    try:
        res = requests.get(f"{API_BASE}/movies", timeout=5)
        if res.status_code == 200:
            return res.json().get("movies", [])
    except Exception:
        pass
    return []


def fetch_movie_detail(movie_id: int):
    """영화 상세 정보 가져오기"""
    try:
        res = requests.get(f"{API_BASE}/movies/{movie_id}", timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


def send_chat(question: str, movie_title: str = None):
    """챗봇 API 호출"""
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


def run_grounding(movie_id: int, category: str):
    """그라운딩 실행"""
    payload = {"movie_id": movie_id, "category": category}
    try:
        res = requests.post(f"{API_BASE}/grounding", json=payload, timeout=30)
        return res.json()
    except Exception as e:
        return {"message": f"오류: {e}", "saved": 0}


# ============================================================
#  세션 상태 초기화
# ============================================================
if "messages" not in st.session_state:
    st.session_state.messages = []   # [{"role": "user"/"bot", "content": str, "sources": str}]

if "selected_movie" not in st.session_state:
    st.session_state.selected_movie = None   # {"movie_id": int, "title": str}


# ============================================================
#  사이드바
# ============================================================
with st.sidebar:
    st.title("🎬 영화 도슨트")
    st.markdown("---")

    # 서버 상태 확인
    try:
        health = requests.get(f"{API_BASE}/health", timeout=3)
        if health.status_code == 200:
            st.success("✅ 서버 연결됨")
        else:
            st.error("❌ 서버 응답 오류")
    except Exception:
        st.error("❌ 서버에 연결할 수 없어요\n`uvicorn main:app --reload` 실행 필요")

    st.markdown("---")

    # 영화 선택
    st.subheader("🎞️ 영화 선택")
    movies = fetch_movies()
    movie_options = ["전체 (영화 미지정)"] + [f"{m['movie_id']}. {m['title']}" for m in movies]
    selected_label = st.selectbox("영화를 선택하세요", movie_options)

    if selected_label != "전체 (영화 미지정)":
        movie_id = int(selected_label.split(".")[0])
        movie_title = selected_label.split(". ", 1)[1]
        st.session_state.selected_movie = {"movie_id": movie_id, "title": movie_title}
    else:
        st.session_state.selected_movie = None

    st.markdown("---")

    # 선택된 영화 상세 정보
    if st.session_state.selected_movie:
        movie_id = st.session_state.selected_movie["movie_id"]
        detail = fetch_movie_detail(movie_id)

        if detail:
            movie = detail.get("movie", {})
            st.subheader(f"📋 {movie.get('title', '')}")
            st.write(f"**감독**: {movie.get('director', '정보 없음')}")
            st.write(f"**장르**: {movie.get('genre', '정보 없음')}")
            st.write(f"**개봉일**: {movie.get('release_date', '정보 없음')}")
            st.write(f"**TMDB 평점**: ⭐ {movie.get('tmdb_rating', '정보 없음')}")

            # TMI 그라운딩
            st.markdown("---")
            st.subheader("🔍 TMI 실시간 검색")
            tmi_category = st.selectbox(
                "카테고리",
                ["촬영지", "OST", "비하인드", "옥에티", "캐스팅비화"],
                key="tmi_cat"
            )
            if st.button("🔄 최신 정보 검색"):
                with st.spinner("검색 중..."):
                    result = run_grounding(movie_id, tmi_category)
                    st.success(f"{result.get('message', '')} ({result.get('saved', 0)}건 저장)")

    st.markdown("---")
    if st.button("🗑️ 대화 초기화"):
        st.session_state.messages = []
        st.rerun()


# ============================================================
#  메인 화면
# ============================================================
st.title("🎬 영화 도슨트 챗봇")

# 선택 영화 안내
if st.session_state.selected_movie:
    st.info(f"💬 현재 대화 중인 영화: **{st.session_state.selected_movie['title']}**")
else:
    st.info("💬 사이드바에서 영화를 선택하거나, 자유롭게 질문하세요!")

# 예시 질문 버튼
st.markdown("**빠른 질문 예시:**")
quick_cols = st.columns(4)
quick_questions = [
    "이 영화 볼만해?",
    "촬영지가 어디야?",
    "OST 어때?",
    "캐스팅 비화 알려줘",
]
for i, q in enumerate(quick_questions):
    if quick_cols[i].button(q, key=f"quick_{i}"):
        st.session_state.messages.append({"role": "user", "content": q, "sources": ""})
        movie_title = st.session_state.selected_movie["title"] if st.session_state.selected_movie else None
        result = send_chat(q, movie_title)
        if result:
            cached_label = " *(캐시)*" if result.get("cached") else ""
            st.session_state.messages.append({
                "role": "bot",
                "content": result["answer"] + cached_label,
                "sources": result.get("sources", "")
            })
        st.rerun()

st.markdown("---")

# ──────────────────────────────────
# 대화 기록 출력
# ──────────────────────────────────
chat_container = st.container()
with chat_container:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="chat-bubble-user">🧑 {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="chat-bubble-bot">🎬 {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
            if msg.get("sources"):
                st.markdown(
                    f'<div class="source-tag">📎 출처: {msg["sources"]}</div>',
                    unsafe_allow_html=True,
                )

# ──────────────────────────────────
# 입력창
# ──────────────────────────────────
st.markdown("---")
with st.form("chat_form", clear_on_submit=True):
    col1, col2 = st.columns([5, 1])
    user_input = col1.text_input(
        "질문을 입력하세요",
        placeholder="예) 파묘 촬영지가 어디야? / 이 영화 무서워?",
        label_visibility="collapsed"
    )
    submitted = col2.form_submit_button("전송 💬")

if submitted and user_input.strip():
    question = user_input.strip()
    st.session_state.messages.append({"role": "user", "content": question, "sources": ""})

    movie_title = st.session_state.selected_movie["title"] if st.session_state.selected_movie else None

    with st.spinner("답변 생성 중..."):
        result = send_chat(question, movie_title)

    if result:
        cached_label = " *(캐시)*" if result.get("cached") else ""
        st.session_state.messages.append({
            "role": "bot",
            "content": result["answer"] + cached_label,
            "sources": result.get("sources", "")
        })
    else:
        st.session_state.messages.append({
            "role": "bot",
            "content": "답변을 가져오지 못했어요. 서버 상태를 확인해주세요.",
            "sources": ""
        })

    st.rerun()


# ──────────────────────────────────
# 영화 상세 탭 (선택된 경우)
# ──────────────────────────────────
if st.session_state.selected_movie:
    st.markdown("---")
    movie_id = st.session_state.selected_movie["movie_id"]
    detail = fetch_movie_detail(movie_id)

    if detail:
        tab1, tab2 = st.tabs(["📝 인기 리뷰 Top 10", "🎭 TMI 정보"])

        with tab1:
            reviews = detail.get("top_reviews", [])
            if reviews:
                for r in reviews:
                    with st.container():
                        rating_str = f"⭐ {r['rating']}" if r.get("rating") else "별점 없음"
                        st.markdown(f"""
                        <div class="movie-card">
                            <b>{r.get('reviewer_nickname', '익명')}</b> &nbsp; {rating_str} &nbsp;
                            👍 {r.get('likes_count', 0)}<br>
                            {r.get('content', '')}
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.write("리뷰가 없어요.")

        with tab2:
            tmi_list = detail.get("tmi", [])
            if tmi_list:
                # 카테고리별로 묶기
                tmi_by_cat = {}
                for t in tmi_list:
                    cat = t.get("category", "기타")
                    tmi_by_cat.setdefault(cat, []).append(t)

                for cat, items in tmi_by_cat.items():
                    with st.expander(f"📌 {cat} ({len(items)}건)"):
                        for item in items:
                            st.write(item.get("content", ""))
                            if item.get("source_url"):
                                st.markdown(f"[출처 링크]({item['source_url']})", unsafe_allow_html=False)
                            st.markdown("---")
            else:
                st.write("TMI 정보가 없어요. 사이드바에서 실시간 검색을 눌러보세요!")