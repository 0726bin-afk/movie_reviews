import json
import os

LGU_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(LGU_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
target_path = os.path.join(DATA_DIR, "cleaned_total_reviews.json")
report_path = os.path.join(LGU_DIR, "data_error_report.txt")

def run_integrity_check():
    if not os.path.exists(target_path):
        print(f"❌ '{target_path}' 파일이 없습니다.")
        return

    with open(target_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    anomaly_report = []

    print("🔍 데이터 무결성 검사 진행 중...")
    for movie, content in data.items():
        meta = content.get("movie_metadata", {})
        movie_id = meta.get("movie_id", "알수없음")
        title = meta.get("title", movie)
        
        # 1. 포스터 누락 및 유효성 검사
        poster_url = meta.get("poster_url")
        if not poster_url or not str(poster_url).startswith("http"):
            anomaly_report.append(f"[포스터 오류] 영화 ID: {movie_id} / 제목: {title} -> 저장된 URL: {poster_url}")
            
        # 2. 필수 메타데이터(줄거리, 주요 스태프 등) 누락 검사
        if not meta.get("overview") or len(meta.get("overview", "")) < 10:
            anomaly_report.append(f"[줄거리 누락] 영화 ID: {movie_id} / 제목: {title} -> 줄거리가 없거나 너무 짧습니다.")
            
        if not meta.get("directors"):
            anomaly_report.append(f"[감독 누락] 영화 ID: {movie_id} / 제목: {title} -> 감독 정보가 없습니다.")
            
        # 3. 리뷰 유무 확인
        revs = content.get('reviews', [])
        if not revs:
            anomaly_report.append(f"[리뷰 없음] 영화 ID: {movie_id} / 제목: {title} -> 수집된 리뷰가 0건입니다.")

    # 레포트 파일 출력
    with open(report_path, "w", encoding="utf-8") as rf:
        if anomaly_report:
            rf.write("⚠️ 데이터 무결성 오류 및 누락 내역 보고서 ⚠️\n")
            rf.write("="*50 + "\n")
            for line in anomaly_report:
                rf.write(line + "\n")
        else:
            rf.write("✅ 모든 데이터가 유효성 검사를 통과했습니다. 누락된 부분이 없습니다.\n")
    print(f"📊 무결성 검사 완료. 제보 내역 저장됨: {report_path}")

if __name__ == "__main__":
    run_integrity_check()
