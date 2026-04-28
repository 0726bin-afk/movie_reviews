"""
Streamlit 챗봇 프론트엔드.

CJB가 작성한 원본(streamlit_app.py)을 기반으로,
`send_chat`만 SSE 스트리밍으로 교체. 나머지 UI/UX는 그대로 유지.

원본 대비 변경점:
  - `send_chat` 동기 JSON → `send_chat_stream` SSE 제너레이터
  - 챗 메시지 렌더링: 누적 문자열을 placeholder.markdown으로 갱신해
    "타자 치듯" 효과 (현재는 final 이벤트로 전체 답변 한 번에. token 이벤트 활성 시 자동으로 글자 단위 갱신)
  - session_id를 st.session_state에 보관 → 멀티턴 컨텍스트 유지
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import requests
import streamlit as st

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
    """영화 목록 가져오기 (1분 캐시)."""
    try:
        res = requests.get(f"{API_BASE}/movies", timeout=5)
        if res.status_code == 200:
            return res.json().get("movies", [])
    except Exception:
        pass
    return []


def fetch_movie_detail(movie_id: int):
    """영화 상세 정보 가져오기."""
    try:
        res = requests.get(f"{API_BASE}/movies/{movie_id}", timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


def run_grounding(movie_id: int, category: str):
    """그라운딩 실행 — 운영자용 수동 트리거."""
    payload = {"movie_id": movie_id, "category": category}
    try:
        res = requests.post(f"{API_BASE}/grounding", json=payload, timeout=30)
        return res.json()
    except Exception as e:
        return {"message": f"오류: {e}", "saved": 0}


# ------------------------------------------------------------
#  ⭐ SSE 스트리밍 챗봇 호출 — 핵심 변경점
# ------------------------------------------------------------
def send_chat_stream(
    question: str,
    session_id: str,
    movie_title: str | None = None,
) -> Iterator[tuple[str, dict]]:
    """
    /chat 엔드포인트에 SSE 요청 후 (event_type, data) 튜플을 yield.

    이벤트 종류:
      - 'node':      노드 진입/종료 신호
      - 'cache_hit': 캐시 히트 시
      - 'token':     LLM 토큰 (Phase 5 generate.astream 활성 시)
      - 'final':     최종 답변·출처
      - 'error':     예외
    """
    payload: dict = {"question": question, "session_id": session_id}
    if movie_title:
        payload["movie_title"] = movie_title

    try:
        with requests.post(
            f"{API_BASE}/chat",
            json=payload,
            stream=True,
            timeout=60,
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code != 200:
                yield "error", {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
                return

            event_type = "message"
            for raw_line in response.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                if raw_line == "":
                    # 이벤트 구분자(빈 줄). 다음 event line까지 message가 default.
                    event_type = "message"
                    continue
                if raw_line.startswith("event:"):
                    event_type = raw_line[6:].strip()
                elif raw_line.startswith("data:"):
                    raw_data = raw_line[5:].strip()
                    try:
                        data = json.loads(raw_data)
                    except json.JSONDecodeError:
                        data = {"raw": raw_data}
                    yield event_type, data
    except Exception as e:
        yield "error", {"error": f"API 연결 오류: {e}"}


# ============================================================
#  세션 상태 초기화
# ============================================================
if "messages" not in st.session_state:
    st.session_state.messages = []   # [{role, content, sources}, ...]

if "selected_movie" not in st.session_state:
    st.session_state.selected_movie = None

if "session_id" not in st.session_state:
    # 세션마다 고유 ID — LangGraph Checkpointer thread_id로 사용
    st.session_state.session_id = f"st-{uuid.uuid4().hex[:12]}"


# ============================================================
#  사이드바
# ============================================================
with st.sidebar:
    st.title("🎬 영화 도슨트")
    st.caption(f"세션: `{st.session_state.session_id[:16]}…`")
    st.markdown("---")

    # 서버 상태 확인
    try:
        h = requests.get(f"{API_BASE}/health", timeout=3)
        if h.status_code == 200:
            st.success("✅ 서버 연결됨")
        else:
            st.error("❌ 서버 응답 오류")
    except Exception:
        st.error("❌ 서버에 연결할 수 없어요\n`uvicorn api.main:app --reload`")

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

            st.markdown("---")
            st.subheader("🔍 TMI 실시간 검색")
            tmi_category = st.selectbox(
                "카테고리",
                ["촬영지", "OST", "비하인드", "옥에티", "캐스팅비화"],
                key="tmi_cat",
            )
            if st.button("🔄 최신 정보 검색"):
                with st.spinner("검색 중..."):
                    result = run_grounding(movie_id, tmi_category)
                    st.success(f"{result.get('message', '')} ({result.get('saved', 0)}건 저장)")

    st.markdown("---")
    if st.button("🗑️ 대화 초기화"):
        st.session_state.messages = []
        st.session_state.session_id = f"st-{uuid.uuid4().hex[:12]}"
        st.rerun()


# ============================================================
#  메인 화면
# ============================================================
st.title("🎬 영화 도슨트 챗봇")

if st.session_state.selected_movie:
    st.info(f"💬 현재 대화 중인 영화: **{st.session_state.selected_movie['title']}**")
else:
    st.info("💬 사이드바에서 영화를 선택하거나, 자유롭게 질문하세요!")


# ------------------------------------------------------------
#  대화 기록 출력 (이전 메시지)
# ------------------------------------------------------------
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
                src_text = msg["sources"] if isinstance(msg["sources"], str) else ", ".join(
                    s.get("snippet", "")[:30] for s in msg["sources"][:3]
                )
                st.markdown(
                    f'<div class="source-tag">📎 출처: {src_text}</div>',
                    unsafe_allow_html=True,
                )


# ------------------------------------------------------------
#  입력창
# ------------------------------------------------------------
st.markdown("---")
with st.form("chat_form", clear_on_submit=True):
    col1, col2 = st.columns([5, 1])
    user_input = col1.text_input(
        "질문을 입력하세요",
        placeholder="예) 파묘 촬영지가 어디야? / 이 영화 무서워?",
        label_visibility="collapsed",
    )
    submitted = col2.form_submit_button("전송 💬")


# ------------------------------------------------------------
#  ⭐ 제출 처리 — SSE 스트리밍으로 답변 받아 typewriter 렌더링
# ------------------------------------------------------------
if submitted and user_input.strip():
    question = user_input.strip()
    st.session_state.messages.append({"role": "user", "content": question, "sources": ""})

    # 사용자 메시지 즉시 출력
    with chat_container:
        st.markdown(
            f'<div class="chat-bubble-user">🧑 {question}</div>',
            unsafe_allow_html=True,
        )

    movie_title = (
        st.session_state.selected_movie["title"]
        if st.session_state.selected_movie else None
    )

    # 봇 답변용 placeholder — 스트리밍 중에 갱신
    with chat_container:
        bot_placeholder = st.empty()
        status_placeholder = st.empty()

    accumulated = ""        # token 이벤트로 흘러올 누적 텍스트
    final_answer = ""       # final 이벤트로 도착한 정확한 답변
    final_sources: list = []
    cache_hit = False
    error_msg: str | None = None

    for event_type, data in send_chat_stream(
        question=question,
        session_id=st.session_state.session_id,
        movie_title=movie_title,
    ):
        if event_type == "node":
            node = data.get("node", "")
            status_placeholder.caption(f"⚙️ {node}…")

        elif event_type == "cache_hit":
            cache_hit = True
            status_placeholder.caption(
                f"⚡ 캐시 히트 ({data.get('source')}, score={data.get('score')})"
            )

        elif event_type == "token":
            # Phase 5 generate.astream 활성 시 글자 단위로 흐름
            accumulated += data.get("text", "")
            bot_placeholder.markdown(
                f'<div class="chat-bubble-bot">🎬 {accumulated}▍</div>',
                unsafe_allow_html=True,
            )

        elif event_type == "final":
            final_answer = data.get("answer", "") or accumulated
            final_sources = data.get("sources", [])
            cache_label = " *(캐시)*" if cache_hit or data.get("cache_hit") else ""
            bot_placeholder.markdown(
                f'<div class="chat-bubble-bot">🎬 {final_answer}{cache_label}</div>',
                unsafe_allow_html=True,
            )

        elif event_type == "error":
            error_msg = data.get("error", "알 수 없는 오류")
            bot_placeholder.error(f"❌ {error_msg}")
            break

    status_placeholder.empty()

    # 메시지 히스토리에 저장 (다음 rerun에서도 보이게)
    if not error_msg:
        st.session_state.messages.append({
            "role": "bot",
            "content": final_answer or accumulated or "(빈 답변)",
            "sources": final_sources,
        })


# ============================================================
#  영화 상세 탭 (선택 시)
# ============================================================
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
                tmi_by_cat: dict = {}
                for t in tmi_list:
                    cat = t.get("category", "기타")
                    tmi_by_cat.setdefault(cat, []).append(t)

                for cat, items in tmi_by_cat.items():
                    with st.expander(f"📌 {cat} ({len(items)}건)"):
                        for item in items:
                            st.write(item.get("content", ""))
                            if item.get("source_url"):
                                st.markdown(f"[출처 링크]({item['source_url']})")
                            st.markdown("---")
            else:
                st.write("TMI 정보가 없어요. 사이드바에서 실시간 검색을 눌러보세요!")
