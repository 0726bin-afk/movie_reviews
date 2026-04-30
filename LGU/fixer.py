import os
import re
import json
import time
import requests
from dotenv import load_dotenv

LGU_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(LGU_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
ORIGINAL_DIR = os.path.join(DATA_DIR, "original")
REPORT_PATH = os.path.join(LGU_DIR, "data_error_report.txt")
MANUAL_FORM_PATH = os.path.join(LGU_DIR, "manual_fix_form.txt")
FIX_REPORT_PATH = os.path.join(LGU_DIR, "fix_report.txt")

load_dotenv(os.path.join(ROOT_DIR, ".env"))
TMDB_KEY = os.getenv("TMDB_KEY")
KOBIS_KEY = os.getenv("KOBIS_KEY")

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def parse_error_report():
    if not os.path.exists(REPORT_PATH):
        return {}
    errors = {}
    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if "영화 ID:" in line:
                m = re.search(r'\[(.*?)\] 영화 ID: (.*?) / 제목: (.*?) ->', line)
                if m:
                    err_type = m.group(1).strip()
                    movie_id = m.group(2).strip()
                    title = m.group(3).strip()
                    if title not in errors:
                        errors[title] = {"movie_id": movie_id, "missing": []}
                    if "포스터" in err_type:
                        errors[title]["missing"].append("poster_url")
                    elif "줄거리" in err_type:
                        errors[title]["missing"].append("overview")
                    elif "감독" in err_type:
                        errors[title]["missing"].append("directors")
    return errors

def fetch_from_api(title, movie_id, missing_fields):
    updates = {}
    
    # TMDB for poster and overview
    if ("poster_url" in missing_fields or "overview" in missing_fields) and TMDB_KEY:
        tmdb_url = "https://api.themoviedb.org/3/search/movie"
        res = requests.get(tmdb_url, params={"api_key": TMDB_KEY, "query": title, "language": "ko-KR"})
        if res.status_code == 200:
            data = res.json()
            if data.get("results"):
                best = data["results"][0]
                if "poster_url" in missing_fields and best.get("poster_path"):
                    updates["poster_url"] = f"https://image.tmdb.org/t/p/w500{best['poster_path']}"
                if "overview" in missing_fields and best.get("overview") and len(best.get("overview", "")) >= 10:
                    updates["overview"] = best.get("overview")

    # KOBIS for directors
    if "directors" in missing_fields and KOBIS_KEY:
        kobis_url = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json"
        res = requests.get(kobis_url, params={"key": KOBIS_KEY, "movieCd": movie_id})
        if res.status_code == 200:
            data = res.json()
            movie_info = data.get("movieInfoResult", {}).get("movieInfo", {})
            directors = movie_info.get("directors", [])
            if directors:
                updates["directors"] = [{"peopleNm": d["peopleNm"], "peopleNmEn": d.get("peopleNmEn", "")} for d in directors]

    return updates

def create_manual_form(manual_queue):
    with open(MANUAL_FORM_PATH, "w", encoding="utf-8") as f:
        f.write("=== 수동 입력 양식 ===\n")
        f.write("아래 빈칸(____)을 지우고 적절한 데이터를 채워주세요.\n")
        f.write("입력하기 어려운 항목은 그대로 두셔도 됩니다.\n\n")
        for title, info in manual_queue.items():
            f.write(f"[{title}]\n")
            if "poster_url" in info["missing"]:
                f.write(f"poster_url: ____\n")
            if "overview" in info["missing"]:
                f.write(f"overview: ____\n")
            if "directors" in info["missing"]:
                f.write(f"directors(쉼표로 구분): ____\n")
            f.write("\n")

def read_manual_form():
    updates_by_title = {}
    if not os.path.exists(MANUAL_FORM_PATH):
        return updates_by_title
    
    with open(MANUAL_FORM_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    current_title = None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("===") or line.startswith("아래 빈칸") or line.startswith("입력하기"):
            continue
            
        if line.startswith("[") and line.endswith("]"):
            current_title = line[1:-1]
            updates_by_title[current_title] = {}
        elif current_title and ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val and val != "____":
                if key.startswith("directors"):
                    updates_by_title[current_title]["directors"] = [{"peopleNm": d.strip(), "peopleNmEn": ""} for d in val.split(",")]
                else:
                    updates_by_title[current_title][key] = val
                    
    return updates_by_title

def main():
    print("🛠️ 오류 수정 스크립트 시작")
    errors = parse_error_report()
    if not errors:
        print("✅ 레포트에서 찾은 오류가 없습니다.")
        return
        
    manual_queue = {}
    fixed_log = []
    
    for title, info in errors.items():
        movie_id = info["movie_id"]
        missing_fields = info["missing"]
        
        safe_title = sanitize_filename(title)
        original_file = os.path.join(ORIGINAL_DIR, f"{safe_title}_리뷰.json")
        
        if not os.path.exists(original_file):
            print(f"⚠️ 원본 파일 없음: {original_file}")
            continue
            
        with open(original_file, "r", encoding="utf-8") as f:
            movie_data = json.load(f)
            
        metadata = movie_data.get("영화_정보", {})
        
        # 원본 파일에서 실제로 데이터가 누락되었는지 재확인
        actually_missing = []
        if "poster_url" in missing_fields:
            p = metadata.get("poster_url")
            if not p or not str(p).startswith("http"):
                actually_missing.append("poster_url")
        if "overview" in missing_fields:
            o = metadata.get("overview")
            if not o or len(o) < 10:
                actually_missing.append("overview")
        if "directors" in missing_fields:
            d = metadata.get("directors")
            if not d:
                actually_missing.append("directors")
                
        if not actually_missing:
            print(f"✅ '{title}' 데이터는 원본 파일에 정상적으로 존재합니다.")
            continue
            
        print(f"🔍 API로 '{title}' 누락 데이터 요청 중... ({actually_missing})")
        api_updates = fetch_from_api(title, movie_id, actually_missing)
        
        still_missing = []
        for field in actually_missing:
            if field in api_updates:
                metadata[field] = api_updates[field]
                fixed_log.append(f"[{title}] API로 '{field}' 자동 수정 완료")
            else:
                still_missing.append(field)
                
        # API에서 찾은 정보가 있다면 원본 JSON 업데이트
        if api_updates:
            with open(original_file, "w", encoding="utf-8") as f:
                json.dump(movie_data, f, ensure_ascii=False, indent=4)
                
        if still_missing:
            manual_queue[title] = {"movie_id": movie_id, "missing": still_missing, "file_path": original_file}
            
    if manual_queue:
        create_manual_form(manual_queue)
        print("\n" + "="*60)
        print(f"⚠️ API에서도 찾을 수 없는 누락 데이터가 {len(manual_queue)}편 있습니다.")
        print(f"[{MANUAL_FORM_PATH}] 파일이 생성되었습니다.")
        print("해당 텍스트 파일을 열고 ____ 부분을 직접 채운 후 저장해주세요.")
        print("="*60 + "\n")
        
        # 윈도우 환경에서 텍스트 파일 자동 실행
        try:
            os.startfile(MANUAL_FORM_PATH)
        except AttributeError:
            import subprocess, sys
            if sys.platform.startswith('darwin'):
                subprocess.call(('open', MANUAL_FORM_PATH))
            elif os.name == 'posix':
                subprocess.call(('xdg-open', MANUAL_FORM_PATH))
        
        input("입력과 저장을 마치셨다면 [Enter] 키를 누르세요...")
        
        manual_updates = read_manual_form()
        for title, updates in manual_updates.items():
            if not updates or title not in manual_queue:
                continue
                
            orig_file = manual_queue[title]["file_path"]
            with open(orig_file, "r", encoding="utf-8") as f:
                movie_data = json.load(f)
                
            metadata = movie_data.get("영화_정보", {})
            for k, v in updates.items():
                metadata[k] = v
                fixed_log.append(f"[{title}] 수동입력으로 '{k}' 수정 완료")
                
            with open(orig_file, "w", encoding="utf-8") as f:
                json.dump(movie_data, f, ensure_ascii=False, indent=4)
                
    # 픽스 완료 후 정리 파트
    with open(FIX_REPORT_PATH, "w", encoding="utf-8") as f:
        if fixed_log:
            f.write("🛠️ 데이터 수정 및 복구 결과 보고서 🛠️\n")
            f.write("="*50 + "\n")
            for log in fixed_log:
                f.write(log + "\n")
        else:
            f.write("수정된 데이터가 없습니다.\n")
            
    print(f"\n📊 데이터 복구 내역 보고서가 저장되었습니다: {FIX_REPORT_PATH}")
    
    print("\n🔄 수정된 원본을 바탕으로 통합 JSON(cleaned_total_reviews.json)을 다시 생성합니다.")
    try:
        import cleaner
        cleaner.process_reviews()
    except Exception as e:
        print("❌ cleaner.py 실행 실패. 수동으로 실행해주세요.", e)
        
    print("\n🔄 무결성 검사를 다시 진행하여 누락이 완전히 해결되었는지 확인합니다.")
    try:
        import checker
        checker.run_integrity_check()
    except Exception as e:
        print("❌ checker.py 실행 실패. 수동으로 실행해주세요.", e)

if __name__ == "__main__":
    main()
