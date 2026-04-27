-- ============================================================
--  영화 도슨트 챗봇 — DB 스키마
--  DB: Supabase (PostgreSQL)
--  최종 업데이트: 2026-04-27
-- ============================================================


-- ============================================================
--  1. 영화 기본 정보 (TMDB API 연동, 35편)
-- ============================================================
CREATE TABLE movies (
    movie_id     SERIAL PRIMARY KEY,
    title        VARCHAR(200) NOT NULL,
    genre        VARCHAR(100),               -- 예: '오컬트', '액션', 'SF' (TMDB 장르 최대 3개)
    director     VARCHAR(100),
    release_date DATE,
    tmdb_rating  DECIMAL(3,1),              -- TMDB 기준 평점 (0.0 → NULL 처리)
    tmdb_id      INT UNIQUE,                -- TMDB 원본 ID (중복 방지)
    cast_members TEXT,                      -- 출연진 상위 7명, 쉼표 구분
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_movies_title ON movies(title);


-- ============================================================
--  2. 리뷰 원문 (크롤러 수집 결과)
-- ============================================================
CREATE TABLE reviews (
    review_id         SERIAL PRIMARY KEY,
    movie_id          INT NOT NULL REFERENCES movies(movie_id),
    reviewer_nickname VARCHAR(100),
    rating            DECIMAL(2,1),          -- 별점 없음 → NULL
    likes_count       INT DEFAULT 0,
    comments_count    INT DEFAULT 0,
    content           TEXT NOT NULL,
    sort_type         VARCHAR(30),           -- '좋아요 순', '높은 평가 순' 등 수집 기준
    collected_at      TIMESTAMP DEFAULT NOW(),

    UNIQUE (movie_id, reviewer_nickname)
);

CREATE INDEX idx_reviews_movie_id ON reviews(movie_id);
CREATE INDEX idx_reviews_rating   ON reviews(rating);
CREATE INDEX idx_reviews_likes    ON reviews(likes_count DESC);


-- ============================================================
--  3. TMI 도슨트 정보 (나무위키 + Gemini 추출 / 그라운딩 저장)
--     카테고리: 촬영지 / OST / 비하인드 / 옥에티 / 캐스팅비화
-- ============================================================
CREATE TABLE movie_tmi (
    tmi_id     SERIAL PRIMARY KEY,
    movie_id   INT NOT NULL REFERENCES movies(movie_id),
    category   VARCHAR(50) NOT NULL,
    content    TEXT NOT NULL,
    source_url VARCHAR(500),                -- 출처 URL (여러 개면 ';' 구분)
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tmi_movie_id ON movie_tmi(movie_id);
CREATE INDEX idx_tmi_category ON movie_tmi(category);


-- ============================================================
--  4. 챗봇 QA 로그 (캐싱 및 대화 기록)
-- ============================================================
CREATE TABLE qa_log (
    log_id     SERIAL PRIMARY KEY,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    sources    TEXT,                        -- 참조 출처 (선택)
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_qa_question ON qa_log(question);


-- ============================================================
--  5. 리뷰 키워드 분류 (RAG팀이 분석 후 INSERT 예정)
-- ============================================================
CREATE TABLE review_keywords (
    keyword_id SERIAL PRIMARY KEY,
    review_id  INT NOT NULL REFERENCES reviews(review_id),
    category   VARCHAR(50)  NOT NULL,       -- '연기', '연출', '서사', '고증', '감성', '기술'
    keyword    VARCHAR(100) NOT NULL,
    sentiment  SMALLINT DEFAULT 0           -- 1=긍정 / -1=부정 / 0=중립
        CHECK (sentiment IN (1, -1, 0))
);

CREATE INDEX idx_kw_review_id ON review_keywords(review_id);
CREATE INDEX idx_kw_category  ON review_keywords(category);
CREATE INDEX idx_kw_keyword   ON review_keywords(keyword);


-- ============================================================
--  6. 민감/편의 정보 플래그 (현재 미사용, v2 예정)
--     예: "부모님과 볼 건데 민망한 장면이 있어?"
-- ============================================================
CREATE TABLE movie_flags (
    flag_id   SERIAL PRIMARY KEY,
    movie_id  INT NOT NULL REFERENCES movies(movie_id),
    flag_type VARCHAR(50) NOT NULL,         -- '노출', '베드신', '쿠키', '아동등장' 등
    has_flag  BOOLEAN DEFAULT FALSE,
    detail    TEXT
);

CREATE INDEX idx_flags_movie_id  ON movie_flags(movie_id);
CREATE INDEX idx_flags_flag_type ON movie_flags(flag_type);
