"""
임베딩 적재 파이프라인 — reviews 테이블 → review_embeddings 테이블.

흐름:
  1. reviews 테이블 SELECT (이미 review_embeddings에 있는 review_id 제외)
  2. review_embeddings에 들어갈 메타 컬럼은 movies JOIN으로 채움
  3. 리뷰 본문을 배치로 임베딩 (Gemini text-embedding-004, 768차원)
  4. review_embeddings INSERT (배치 단위 commit)
  5. 부분 실패 시 다음 배치로 넘어감 — 진행률·실패 카운트 출력

실행:
  python -m ingestion.embedding.run                    # 미임베딩 리뷰 전체
  python -m ingestion.embedding.run --movie-id 1       # 특정 영화만
  python -m ingestion.embedding.run --limit 100        # 100건만
  python -m ingestion.embedding.run --force            # 이미 있어도 재임베딩
  python -m ingestion.embedding.run --batch 50         # 배치 크기 변경

선행 조건:
  - schema.sql 적용 완료 (review_embeddings 테이블 + pgvector 확장)
  - reviews 테이블에 데이터 적재 완료 (CJB insert_reviews.py)
  - GEMINI_API_KEY 설정 (.env)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

from db.client import close_pool, get_pool
from providers.embedding import get_embedding


# ============================================================
# 데이터 fetch
# ============================================================

async def fetch_pending_reviews(
    movie_id: int | None,
    limit: int | None,
    force: bool,
) -> list[dict]:
    """
    아직 임베딩되지 않은 리뷰를 메타 컬럼과 함께 반환.
    --force면 모든 리뷰 (review_embeddings에 이미 있어도 재임베딩 후보).
    """
    pool = await get_pool()
    where: list[str] = []
    params: list = []

    if movie_id is not None:
        params.append(movie_id)
        where.append(f"r.movie_id = ${len(params)}")

    if not force:
        # 이미 임베딩 적재된 review_id는 제외
        where.append(
            "NOT EXISTS (SELECT 1 FROM review_embeddings re WHERE re.review_id = r.review_id)"
        )

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    limit_sql = f"LIMIT {int(limit)}" if limit else ""

    sql = f"""
        SELECT
            r.review_id,
            r.movie_id,
            r.content,
            r.rating,
            r.likes_count AS likes,
            m.title AS movie_nm,
            CASE WHEN m.release_date IS NOT NULL
                 THEN to_char(m.release_date, 'YYYY-MM-DD')
                 ELSE NULL END AS open_dt,
            m.genre AS genre_alt
        FROM reviews r
        LEFT JOIN movies m ON r.movie_id = m.movie_id
        {where_sql}
        ORDER BY r.review_id
        {limit_sql}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]


# ============================================================
# 적재 (배치)
# ============================================================

async def insert_embeddings(
    items: list[dict],
    embeddings: list[list[float]],
    force: bool,
) -> int:
    """
    review_embeddings 다건 INSERT.
    --force면 기존 row 먼저 DELETE 후 INSERT.
    """
    if not items:
        return 0

    pool = await get_pool()
    rows: list[tuple] = []
    for item, vec in zip(items, embeddings):
        # pgvector는 list를 string literal로도 받음. asyncpg + pgvector
        # 둘 다 호환되는 형식: "[0.1,0.2,...]"
        emb_literal = "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
        rows.append((
            item["review_id"],
            item["movie_id"],
            item.get("movie_nm"),
            item.get("open_dt"),
            item.get("genre_alt"),
            float(item["rating"]) if item.get("rating") is not None else None,
            int(item["likes"]) if item.get("likes") is not None else 0,
            item["content"],
            emb_literal,
        ))

    inserted = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            if force:
                ids = [item["review_id"] for item in items]
                await conn.execute(
                    "DELETE FROM review_embeddings WHERE review_id = ANY($1::int[])",
                    ids,
                )
            await conn.executemany(
                """
                INSERT INTO review_embeddings
                    (review_id, movie_id, movie_nm, open_dt, genre_alt,
                     rating, likes, content, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector)
                """,
                rows,
            )
            inserted = len(rows)
    return inserted


# ============================================================
# 메인 루프
# ============================================================

async def run(
    movie_id: int | None,
    limit: int | None,
    force: bool,
    batch_size: int,
) -> None:
    embedder = get_embedding()
    print(f"임베딩 모델: {embedder.model_name} ({embedder.dimension}차원)")
    print(f"옵션: movie_id={movie_id}, limit={limit}, force={force}, batch={batch_size}\n")

    items = await fetch_pending_reviews(movie_id=movie_id, limit=limit, force=force)
    total = len(items)
    if total == 0:
        print("✅ 임베딩 대상 없음 (모든 리뷰가 이미 적재됨 또는 조건 매칭 0건).")
        return

    print(f"🚀 총 {total}건 임베딩 시작\n")

    success = 0
    failed = 0
    t_start = time.perf_counter()

    for i in range(0, total, batch_size):
        batch = items[i : i + batch_size]
        idx = i // batch_size + 1
        print(f"📦 배치 {idx} — {i+1}~{i+len(batch)}/{total} 처리 중...", end=" ", flush=True)

        try:
            texts = [it["content"] for it in batch]
            vecs = await embedder.aembed_documents(texts)
        except Exception as e:
            print(f"❌ 임베딩 실패: {e}")
            failed += len(batch)
            continue

        try:
            n = await insert_embeddings(batch, vecs, force=force)
            success += n
            elapsed = time.perf_counter() - t_start
            rate = success / elapsed if elapsed > 0 else 0
            print(f"✅ {n}건 INSERT (누적 {success}/{total}, {rate:.1f}건/s)")
        except Exception as e:
            print(f"❌ INSERT 실패: {e}")
            failed += len(batch)

    elapsed = time.perf_counter() - t_start
    print(
        f"\n✨ 완료: 성공 {success}건 / 실패 {failed}건 / "
        f"소요 {elapsed:.1f}초 ({success / max(elapsed, 0.001):.1f}건/s)"
    )


# ============================================================
# CLI
# ============================================================

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="리뷰 임베딩 → review_embeddings 적재")
    p.add_argument("--movie-id", type=int, default=None, help="특정 영화만")
    p.add_argument("--limit", type=int, default=None, help="최대 처리 건수")
    p.add_argument("--force", action="store_true", help="이미 있어도 재임베딩")
    p.add_argument("--batch", type=int, default=32, help="배치 크기 (기본 32)")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])

    async def _main():
        try:
            await run(
                movie_id=args.movie_id,
                limit=args.limit,
                force=args.force,
                batch_size=args.batch,
            )
        finally:
            await close_pool()

    asyncio.run(_main())


if __name__ == "__main__":
    main()
