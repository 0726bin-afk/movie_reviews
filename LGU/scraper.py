from playwright.sync_api import sync_playwright
import os
import json
import time
import random
import re
import requests
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(os.path.join("..", ".env"))

# 환경 변수 설정
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
PASSWORD = os.getenv("PASSWORD")
KOBIS_KEY = os.getenv("KOBIS_KEY")

# 설정
DATA_DIR = os.path.join("..", "data", "original")
MOVIE_LIST_PATH = "movie_list.txt"

# 파일 이름 사용 불가 문자 제거 함수
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# 재시도 로직을 포함한 안전한 GET 요청 함수
def safe_get(url, params=None, max_retries=3):
    for i in range(max_retries):
        try:
            response = requests.get(url, params=params)
            if response.status_code == 429:
                wait_time = (i + 1) * 3 + random.random()
                time.sleep(wait_time)
                continue
            response.raise_for_status()
            return response.json()
        except:
            time.sleep(2)
    return None

# KOBIS 및 TMDB 메타데이터
def get_rich_metadata(movie_title, search_year=None):
    print(f"🎬 '{movie_title}' 메타데이터 조회 중...")
    def query_kobis(title, year=None):
        search_url = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieList.json"
        clean_title = re.sub(r'[*]', '', title)
        res = safe_get(search_url, params={"key": KOBIS_KEY, "movieNm": clean_title, "itemPerPage": "100"})
        if not res: return None
        movie_list = res.get("movieListResult", {}).get("movieList", [])
        if not movie_list: return None
        target = title.replace(" ", "")
        for m in movie_list:
            if m["movieNm"].replace(" ", "") == target:
                if year and (m.get("prdtYear") == str(year) or m.get("openDt", "")[:4] == str(year)):
                    return m
        for m in movie_list:
            if m["movieNm"].replace(" ", "") == target:
                return m
        return movie_list[0] if movie_list else None

    best_match = query_kobis(movie_title, search_year)
    tmdb_fallback = None
    if not best_match:
        tmdb_url = "https://api.themoviedb.org/3/search/movie"
        if os.getenv("TMDB_KEY"):
            tmdb_res = safe_get(tmdb_url, {"api_key": os.getenv("TMDB_KEY"), "query": movie_title, "language": "ko-KR", "year": search_year})
            if tmdb_res and tmdb_res.get("results"):
                tmdb_fallback = tmdb_res["results"][0]
                best_match = query_kobis(tmdb_fallback["title"], tmdb_fallback.get("release_date", "")[:4])

    if not best_match and tmdb_fallback:
        return {"movieNm": tmdb_fallback["title"], "prdtYear": tmdb_fallback.get("release_date", "")[:4], "movieCd": str(tmdb_fallback["id"])}
    if not best_match: return None

    print(f"✅ KOBIS 매칭 성공: {best_match['movieNm']}")
    info_url = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json"
    k_res = safe_get(info_url, {"key": KOBIS_KEY, "movieCd": best_match["movieCd"]})
    kobis_data = k_res.get("movieInfoResult", {}).get("movieInfo", {}) if k_res else {}
    
    # TMDB 데이터 보강 (줄거리, 포스터)
    tmdb_extra = {"overview": "", "poster_path": ""}
    if os.getenv("TMDB_KEY"):
        try:
            tmdb_url = "https://api.themoviedb.org/3/search/movie"
            tmdb_params = {
                "api_key": os.getenv("TMDB_KEY"), 
                "query": kobis_data.get("movieNm", movie_title), 
                "language": "ko-KR",
                "year": kobis_data.get("prdtYear") or kobis_data.get("openDt", "")[:4]
            }
            tmdb_res = safe_get(tmdb_url, params=tmdb_params)
            if tmdb_res and tmdb_res.get("results"):
                tmdb_extra["overview"] = tmdb_res["results"][0].get("overview", "")
                tmdb_extra["poster_path"] = f"https://image.tmdb.org/t/p/w500{tmdb_res['results'][0].get('poster_path')}" if tmdb_res["results"][0].get("poster_path") else ""
        except: pass
    
    return {
        "movieCd": kobis_data.get("movieCd"),
        "movieNm": kobis_data.get("movieNm"),
        "movieNmEn": kobis_data.get("movieNmEn"),
        "prdtYear": kobis_data.get("prdtYear"),
        "openDt": kobis_data.get("openDt"),
        "typeNm": kobis_data.get("typeNm"),
        "prdtStatNm": kobis_data.get("prdtStatNm"),
        "nationAlt": ", ".join([n["nationNm"] for n in kobis_data.get("nations", [])]) if kobis_data.get("nations") else "",
        "genreAlt": ", ".join([g["genreNm"] for g in kobis_data.get("genres", [])]) if kobis_data.get("genres") else "",
        "repNationNm": kobis_data.get("nations")[0]["nationNm"] if kobis_data.get("nations") else "",
        "repGenreNm": kobis_data.get("genres")[0]["genreNm"] if kobis_data.get("genres") else "",
        "directors": [{"peopleNm": d["peopleNm"], "peopleNmEn": d.get("peopleNmEn", "")} for d in kobis_data.get("directors", [])],
        "actors": [{"peopleNm": a["peopleNm"], "peopleNmEn": a.get("peopleNmEn", ""), "cast": a.get("cast", ""), "castEn": a.get("castEn", "")} for a in kobis_data.get("actors", [])],
        "staffs": [{"peopleNm": s["peopleNm"], "staffRoleNm": s["staffRoleNm"]} for s in kobis_data.get("staffs", [])],
        "audits": [a["watchGradeNm"] for a in kobis_data.get("audits", [])],
        "companys": [{"companyCd": c["companyCd"], "companyNm": c["companyNm"], "companyPartNm": c.get("companyPartNm", "")} for c in kobis_data.get("companys", [])],
        "showTypes": [s["showTypeNm"] for s in kobis_data.get("showTypes", [])],
        "overview": tmdb_extra["overview"],
        "poster_url": tmdb_extra["poster_path"]
    }

def login_watcha(context, email, password):
    page = context.new_page()
    page.goto("https://pedia.watcha.com/ko-KR")
    page.wait_for_load_state("networkidle")
    
    try:
        page.get_by_role("button", name="로그인").click()
        page.get_by_role("button", name="이메일로 로그인").click()
        page.get_by_placeholder("이메일").fill(email)
        page.get_by_placeholder("비밀번호").fill(password)
        page.locator('button[type="submit"]', has_text="로그인").click()
        page.wait_for_load_state("networkidle")
        print("✅ 왓챠피디아 로그인 완료")
    except Exception as e:
        print(f"❌ 로그인 중 오류 발생: {e}")
    return page

def find_movie_on_watcha(page, search_title, list_year, tmdb_year):
    print(f"🔍 왓챠피디아에서 '{search_title}' 검색 중...")
    import urllib.parse
    encoded_title = urllib.parse.quote(search_title)
    search_url = f"https://pedia.watcha.com/ko/searches/movies?query={encoded_title}"
    page.goto(search_url)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except: pass
    
    if "/contents/" in page.url:
        print("🚀 영화 상세 페이지로 바로 이동되었습니다.")
        return True
    
    items = page.locator('li[class*="_listItem_"]')
    try:
        items.first.wait_for(state="visible", timeout=10000)
    except:
        return False
    
    count = items.count()
    if count == 0: return False

    best_match_idx = -1
    title_match_idx = -1
    
    for i in range(count):
        title_text = items.nth(i).locator('div[class*="_title_"]').inner_text().strip()
        subtitle_text = items.nth(i).locator('div[class*="_subtitle_"]').inner_text().strip()
        y_match = re.search(r'(\d{4})', subtitle_text)
        item_year = y_match.group(1) if y_match else ""
        
        if title_text == search_title:
            if title_match_idx == -1:
                title_match_idx = i # 일단 제목이라도 일치하는 것 저장
            
            # 연도까지 일치하면 최고의 매칭
            if list_year and item_year == list_year:
                best_match_idx = i
                break
            elif tmdb_year and item_year == tmdb_year:
                best_match_idx = i
                break
                
    # 최고의 매칭(연도 포함)이 없으면 제목만 일치하는 첫 번째 영화, 그것도 없으면 그냥 0번을 고름
    final_idx = best_match_idx if best_match_idx != -1 else (title_match_idx if title_match_idx != -1 else 0)
    
    print(f"🎯 선택된 영화 인덱스: {final_idx}")
    items.nth(final_idx).click()
    page.wait_for_load_state("networkidle")
    return True

def scrape_reviews(page, movie_name):
    print(f"📊 '{movie_name}' 리뷰 수집 시작 (목표: 필터당 신규 20개씩)...")
    
    try:
        page.wait_for_url("**/contents/*", timeout=5000)
    except: pass

    movie_id_match = re.search(r'/contents/([a-zA-Z0-9]+)', page.url)
    if movie_id_match:
        movie_id = movie_id_match.group(1)
        base_comments_url = f"https://pedia.watcha.com/ko-KR/contents/{movie_id}/comments"
        if "/comments" not in page.url:
            print(f"🔄 코멘트 페이지 이동: {base_comments_url}")
            page.goto(base_comments_url, wait_until="networkidle")
            page.wait_for_timeout(3000)
    else:
        print("❌ 영화 ID를 찾을 수 없습니다.")
        return []

    sort_options = [
        ("좋아요 순", "favorite"),
        ("유저 반응 순", "recommended"),
        ("높은 평가 순", "high"),
        ("낮은 평가 순", "low"),
        ("최신 순", "recent")
    ]
    
    all_combined_reviews = []
    seen_content = set()
    target_per_filter = 20

    for sort_name, order_param in sort_options:
        print(f"  ➡️ [{sort_name}] 필터 적용 중...")
        
        # UI에서 필터 클릭하기
        filter_changed = False
        try:
            sort_btn = page.locator('button').filter(has_text=re.compile(r"(순|좋아요|인기|별점|최신)$")).first
            if sort_btn.is_visible():
                sort_btn.click()
                page.wait_for_timeout(1000)
                
                # 매핑 텍스트 찾기
                ui_mapping = {"좋아요 순": "좋아요 순", "유저 반응 순": "인기 순", "높은 평가 순": "높은 별점 순", "낮은 평가 순": "낮은 별점 순", "최신 순": "최신 순"}
                target_label = ui_mapping.get(sort_name, sort_name)
                
                menu_item = page.locator('ul[role="listbox"] button, div[class*="_menu_"] button').filter(has_text=re.compile(f"^{target_label}$")).last
                if not menu_item.is_visible():
                    menu_item = page.get_by_text(target_label, exact=True).last
                    
                if menu_item.is_visible():
                    menu_item.click()
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(4000) # 데이터 로딩 대기
                    filter_changed = True
                    print(f"    ✨ '{target_label}' 필터 변경 완료")
        except:
            pass

        # 직접 URL 이동 (UI 클릭 실패 시에만, 최후의 수단)
        if not filter_changed:
            target_url = f"{base_comments_url}?order={order_param}"
            page.goto(target_url, wait_until="networkidle")
            time.sleep(5)

        print(f"    📥 {sort_name} 데이터 수집 중 (목표: 신규 100개)...")
        
        newly_added_this_filter = 0
        scroll_retry = 0
        
        while newly_added_this_filter < target_per_filter:
            reviews_list = page.locator('article[class*="_container_"]')
            current_total = reviews_list.count()
            
            for i in range(current_total):
                if newly_added_this_filter >= target_per_filter: break
                
                try:
                    box = reviews_list.nth(i)
                    content_node = box.locator('.CommentText, div[class*="_content_"]').first
                    if not content_node.count(): continue
                    
                    content = content_node.inner_text().strip()
                    if content in seen_content:
                        continue 
                    
                    is_spoiler = False
                    # 스포일러 버튼
                    if "스포일러" in box.inner_text() and box.get_by_text("보기", exact=True).is_visible():
                        is_spoiler = True
                        box.get_by_text("보기", exact=True).click(timeout=500)
                        content = content_node.inner_text().strip()
                    
                    nickname = ""
                    try:
                        user_links = box.locator("a[href*='/users/']").all()
                        for link in user_links:
                            title = link.get_attribute("title")
                            if title:
                                nickname = title.strip()
                                break
                            text = link.inner_text().strip()
                            if text:
                                nickname = text
                                break
                    except: pass
                    
                    if nickname:
                        nickname = nickname.split('\n')[0].strip()
                    else:
                        nickname = "익명"
                    rating_node = box.locator("div[class*='_rating_'] p, span[class*='_rating_']").first
                    rating = rating_node.inner_text() if rating_node.count() > 0 else "없음"
                    
                    likes_node = box.locator('button:has-text("좋아요"), span:has-text("좋아요")').first
                    likes = "0"
                    if likes_node.count() > 0:
                        lm = re.search(r'(\d+)', likes_node.inner_text())
                        likes = lm.group(1) if lm else "0"

                    all_combined_reviews.append({
                        "리뷰어_닉네임": nickname,
                        "별점": rating,
                        "좋아요_수": likes,
                        "영화_제목": movie_name,
                        "스포일러_포함": is_spoiler,
                        "리뷰_본문_내용": content,
                        "수집_필터": sort_name
                    })
                    seen_content.add(content)
                    newly_added_this_filter += 1
                except:
                    continue
            
            if newly_added_this_filter >= target_per_filter:
                break
                
            if current_total > 0:
                reviews_list.last.scroll_into_view_if_needed()
                page.evaluate("window.scrollBy(0, 1500)")
            else:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
            time.sleep(random.uniform(5.0, 7.0))
            
            new_total = page.locator('article[class*="_container_"]').count()
            if new_total == current_total:
                scroll_retry += 1
                if scroll_retry >= 8:
                    print(f"    📍 스크롤 중단 (더 이상의 스크롤 불가 또는 네트워크 지연): 신규 {newly_added_this_filter}개 확보")
                    break
            else:
                scroll_retry = 0
                
            if newly_added_this_filter % 20 == 0 and newly_added_this_filter > 0:
                 print(f"    ... {sort_name} 진척도: {newly_added_this_filter}/100")

        print(f"    ✅ {sort_name} 완료: 신규 {newly_added_this_filter}개 수집 (현재까지 누적 유니크 데이터: {len(all_combined_reviews)}개)")
        time.sleep(random.uniform(5.0, 8.0))
            
    return all_combined_reviews

def main():
    if not os.path.exists(MOVIE_LIST_PATH):
        print(f"❌ {MOVIE_LIST_PATH} 파일이 없습니다.")
        return

    with open(MOVIE_LIST_PATH, "r", encoding="utf-8") as f:
        movie_lines = [line.strip() for line in f if line.strip()]

    os.makedirs(DATA_DIR, exist_ok=True)

    # 1. 브라우저 구동 (Headless=False로 우회)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = login_watcha(context, EMAIL_ADDRESS, PASSWORD)
        
        for line in movie_lines:
            parts = line.split('|')
            input_title = parts[0]
            list_year = parts[1] if len(parts) > 1 else None
            
            # 메타데이터 수집
            metadata = get_rich_metadata(input_title, list_year)
            if not metadata: continue
            
            official_title = metadata["movieNm"]
            tmdb_year = metadata["prdtYear"]
            
            # 영화 검색 및 이동
            found = find_movie_on_watcha(page, official_title, list_year, tmdb_year)
            if not found: continue
            
            # 리뷰 수집 (필터당 신규 100개 채울 때까지 지속 스크롤)
            reviews = scrape_reviews(page, official_title)
            
            # 데이터 저장
            safe_title = sanitize_filename(official_title)
            save_data = {"영화_정보": metadata, "리뷰_목록": reviews}
            file_path = os.path.join(DATA_DIR, f"{safe_title}_리뷰.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=4)
            
            print(f"✅ '{official_title}' 저장 완료: 총 {len(reviews)}개 고유 리뷰 확보")
            
            # 다음 영화 수집 전 충분한 휴식
            wait_between = random.uniform(20.0, 30.0)
            print(f"💤 수집 완료! {wait_between:.2f}초간 휴식합니다...")
            time.sleep(wait_between)
            
        browser.close()

if __name__ == "__main__":
    main()
