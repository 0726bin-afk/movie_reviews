import json
import os
import re

def clean_text(text):
    """리뷰 본문 텍스트를 정제하는 함수"""
    if not text:
        return ""
    
    # 1. 줄바꿈 및 연속된 공백 제거
    text = re.sub(r'\s+', ' ', text)
    
    # 2. 양끝 공백 제거
    text = text.strip()
    
    # 3. 특수 기호 중 의미 없는 반복 제거 (예: !!! -> !)
    text = re.sub(r'!+', '!', text)
    text = re.sub(r'\?+', '?', text)
    text = re.sub(r'\.+', '.', text)
    
    return text

def convert_to_numeric(value, default=0):
    """문자열 숫자를 수치형으로 변환하는 함수"""
    if not value or value == "없음":
        return default
    try:
        # 천 단위 콤마 제거 및 숫자 추출
        num_str = re.sub(r'[^\d.]', '', value)
        if '.' in num_str:
            return float(num_str)
        return int(num_str)
    except:
        return default

def process_reviews():
    # 🏗️ 경로 설정 (프로젝트 루트 기준)
    LGU_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(LGU_DIR)
    DATA_DIR = os.path.join(ROOT_DIR, "data")
    
    original_dir = os.path.join(DATA_DIR, "original")
    output_file = os.path.join(DATA_DIR, "cleaned_total_reviews.json")
    
    # 데이터 저장 폴더 생성 (공용 data 폴더)
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if not os.path.exists(original_dir):
        print(f"❌ '{original_dir}' 폴더가 존재하지 않습니다. 먼저 scraper.py를 실행해 주세요.")
        return

    import glob
    file_paths = glob.glob(os.path.join(original_dir, "*.json"))

    print(f"📂 총 {len(file_paths)}개의 json 파일을 정제 처리합니다...")

    total_cleaned_data = {}

    for full_path in file_paths:
        if not os.path.isfile(full_path):
            continue
            
        with open(full_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except: continue

            movie_info = data.get("영화_정보", {})
            reviews = data.get("리뷰_목록", [])
            movie_nm = movie_info.get("movieNm", "알 수 없음")
            movie_cd = movie_info.get("movieCd", str(hash(movie_nm)))
            
            # 1. 영화 메타데이터 표준화 (RDB/RAG 태그 및 지식 베이스용)
            open_dt = movie_info.get("openDt", "")
            release_year = int(open_dt[:4]) if open_dt and len(open_dt) >= 4 else 0
            
            # 장르 및 국가 정보 정형화
            genres = [g.strip() for g in movie_info.get("genreAlt", "").split(",") if g.strip()]
            if not genres and movie_info.get("repGenreNm"):
                genres = [movie_info.get("repGenreNm")]
            
            # 배우진 정보 가공 (배우명(배우명En) 또는 배우명(역할))
            actor_list = []
            for actor in movie_info.get("actors", []):
                name = actor.get("peopleNm")
                cast = actor.get("cast")
                actor_list.append(f"{name}({cast})" if cast else name)

            # 관람 등급 추출 (audits 정보 활용)
            audits = movie_info.get("audits", [])
            age_rating = "정보없음"
            if audits:
                age_rating = audits[0] if isinstance(audits[0], str) else audits[0].get("watchGradeNm", "정보없음")

            standard_metadata = {
                "movie_id": movie_cd,
                "title": movie_nm,
                "title_en": movie_info.get("movieNmEn", ""),
                "release_year": release_year,
                "openDt": movie_info.get("openDt", ""),
                "typeNm": movie_info.get("typeNm", ""),
                "prdtStatNm": movie_info.get("prdtStatNm", ""),
                "genres": genres,
                "nations": [n.strip() for n in movie_info.get("nationAlt", "").split(",") if n.strip()],
                "directors": [d.get("peopleNm") for d in movie_info.get("directors", []) if isinstance(d, dict)],
                "actors": actor_list[:15], # 주/조연급인 상위 15명으로 제한
                "staffs": [s for s in movie_info.get("staffs", []) if s.get("staffRoleNm") in ["제작", "프로듀서", "각본", "각색", "감독", "촬영", "조명", "미술", "음악", "편집", "음향", "의상"]], # 주요 스태프 역할만 필터링
                "companys": movie_info.get("companys", []),
                "showTypes": movie_info.get("showTypes", []),
                "age_rating": age_rating,
                "overview": movie_info.get("overview", ""), # 줄거리 추가
                "poster_url": movie_info.get("poster_url"), # 포스터 경로 추가
                "tmdb_rating": convert_to_numeric(str(movie_info.get("tmdb_rating", 0)))
            }
            
            cleaned_movie_reviews = []
            seen_contents = set()
            
            for i, rev in enumerate(reviews):
                original_content = rev.get("리뷰_본문_내용", "")
                cleaned_content = clean_text(original_content)
                
                if not cleaned_content or len(cleaned_content) < 5:
                    continue
                
                if cleaned_content in seen_contents:
                    continue
                seen_contents.add(cleaned_content)
                
                # 2. 리뷰 데이터 수치 변환 및 ID 부여 (Vector DB용)
                cleaned_rev_record = {
                    "review_id": f"{movie_cd}_{i}",
                    "movie_id": movie_cd,
                    "reviewer": rev.get("리뷰어_닉네임"),
                    "rating": convert_to_numeric(rev.get("별점")),
                    "likes": convert_to_numeric(rev.get("좋아요_수")),
                    "comment_count": convert_to_numeric(rev.get("댓글_수")),
                    "is_spoiler": rev.get("스포일러_포함", False),
                    "filter_used": rev.get("수집_필터", ""),
                    "content": cleaned_content,
                    # Self-Querying을 위해 핵심 메타데이터를 리뷰 레벨에 포함
                    "meta_tags": {
                        "title": movie_nm,
                        "year": release_year,
                        "genres": genres,
                        "age_rating": age_rating
                    }
                }
                cleaned_movie_reviews.append(cleaned_rev_record)

            if cleaned_movie_reviews:
                total_cleaned_data[movie_nm] = {
                    "movie_metadata": standard_metadata,
                    "reviews": cleaned_movie_reviews
                }

    # 4. 통합된 하나의 파일로 저장
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(total_cleaned_data, f, ensure_ascii=False, indent=4)
    
    print(f"\n✨ 고도화 정제 완료! '{output_file}'에 RAG/RDB 준비가 완료된 데이터가 저장되었습니다.")

if __name__ == "__main__":
    process_reviews()
