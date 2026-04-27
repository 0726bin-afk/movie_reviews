from playwright.sync_api import sync_playwright
import os
import json
import time
import random

# 💡 내 계정 정보 (실제 사용 시 본인 정보로 바꿔줘!)
EMAIL_ADDRESS = "kkangewq1@gmail.com"
PASSWORD = "kkang-password1"
MOVIE = "왕과 사는 남자"
distribution_input = "70,0,0,0,30" #정렬 기준, [좋아요, 유저 반응, 높은 평가, 낮은 평가, 작성 순]  각각 몇 개씩 추출할 것인지

def go_to_movie_comments(movie_name):
    # 💡 with문을 쓰면 함수 종료 시 브라우저가 닫히므로, start()로 실행해서 창을 유지해!
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False)
    
    # 사용할 신분증 문장을 변수에 예쁘게 담아두기
    my_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # context를 만들 때 user_agent 옵션으로 신분증 건네주기!
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent=my_user_agent  # <--- 바로 여기야!
    )
    page = context.new_page()

    print("1. 평범한 윈도우 유저로 위장해서 왓챠피디아 접속 중... 😎")
    page.goto("https://pedia.watcha.com/ko-KR")

    # 네트워크가 조용해질 때까지 기다린 후, 강제로 2초 더 기다려주기 (팝업이나 애니메이션이 뜰 시간 주기)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    print("🔑 1-5. 로그인 먼저 시원하게 하고 시작하기!")
    # 1. 우측 상단의 '로그인' 버튼 찾아서 누르기
    page.get_by_role("button", name="로그인").click()
    page.get_by_role("button", name="이메일로 로그인").click()
    
    # 2. 이메일과 비밀번호 입력창에 내 정보 채워 넣기
    page.get_by_placeholder("이메일").fill(EMAIL_ADDRESS)
    page.get_by_placeholder("비밀번호").fill(PASSWORD)
    
    # 3. 핑크색 커다란 '로그인' 버튼 누르기
    login_submit_button = page.locator('button[type="submit"]', has_text="로그인")
    login_submit_button.click()
    
    # 로그인 완료 후 화면이 완전히 바뀔 때까지 잠깐 기다리기
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    
    print("2. 메인 화면의 '가짜 검색창(버튼)' 클릭하기!")
    # 플레이라이트가 알려준 가장 확실한 방법!
    fake_search_box = page.get_by_role("link", name="콘텐츠, 인물, 컬렉션, 유저, 매거진 검색")
    fake_search_box.click()

    print(f"3. '진짜 검색창'이 나타나면 '{movie_name}' 입력하기!")
    # 버튼을 누르면 나타나는 진짜 input 창을 찾아서 입력해!
    real_search_box = page.locator('input[name="searchKeyword"]')
    
    # 진짜 창이 나타날 때까지 확실히 기다려주는 센스!
    real_search_box.wait_for() 
    # 💡 하드코딩된 이름 대신 인자로 받은 movie_name을 입력해!
    real_search_box.fill(movie_name)
    real_search_box.press("Enter")
    
    print("4. 검색 결과에서 영화 클릭하기!")
    page.wait_for_selector("div._topTitle_1tope_35", timeout=10000)
    # 💡 여기도 하드코딩 대신 인자로 받은 movie_name으로 찾게 수정했어!
    movie_title = page.locator("div._topTitle_1tope_35", has_text=movie_name).first
    movie_title.click()

    print("5. 평점 더보기 버튼 클릭하기!")
    # 💡 [필수 수정] 기존 코드는 '헤일메리' 고유 주소라서, 모든 영화에서 쓸 수 있게 '/comments로 끝나는 링크'로 찾도록 변경했어.
    page.wait_for_selector('a[href$="/comments"]', timeout=10000)
    more_button = page.locator('a[href$="/comments"]').first
    more_button.click()

    print("🎉 리뷰 창 진입 성공!")
    page.wait_for_timeout(3000)

    # 💡 브라우저를 끄지 않고, 다음 작업을 위해 page 객체를 짠! 하고 반환해.
    return page


def scrape_reviews(page, movie_title, dist_input):
    """설정한 기준에 맞춰 리뷰를 수집하고 저장하는 함수"""
    
    # 1. 입력 파라미터 처리 (예: "7,0,0,0,3" -> 딕셔너리로 변환)
    labels = ['좋아요 순', '유저 반응 순', '높은 평가 순', '낮은 평가 순', '작성 순']
    dist_list = [int(x.strip()) for x in dist_input.split(',')]
    distribution = dict(zip(labels, dist_list))
    
    all_reviews_data = []

    for sort_type, target_count in distribution.items():
        if target_count <= 0:
            continue
            
        print(f"\n🔄 [{sort_type}] 수집 시작 (목표: {target_count}개)")
        
        # [중요] 2. 정렬 변경 전 페이지 맨 위로 스크롤 올리기
        page.keyboard.press("Home")
        time.sleep(1)
        
        # 정렬 기준 탭 클릭
        try:
            current_sort = page.locator("span._title_yyxnf_60").inner_text(timeout=5000)
            if current_sort != sort_type:
                page.locator("span._title_yyxnf_60").click()
                time.sleep(0.5)
                page.locator(f'button:has-text("{sort_type}")').last.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)
        except Exception as e:
            print(f"정렬 변경 중 소소한 문제가 생겼지만 계속 진행할게! : {e}")
        
        # 무한 스크롤 및 3. 스포일러 해제
        review_elements = page.locator("article._container_xsu2o_1")
        
        # 스크롤 멈춤 방지를 위한 인내심 카운터!
        retry_count = 0 
        
        while review_elements.count() < target_count:
            previous_count = review_elements.count()
            
            # 5. 안티 봇: 랜덤 대기 후 확실하게 화면 맨 밑으로 강제 스크롤! (End 키 대신)
            time.sleep(random.uniform(1.0, 1.5))
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
            # 💡 [핵심] 왓챠피디아가 새 리뷰를 로딩할 시간을 충분히 줘야 해!
            time.sleep(random.uniform(2.0, 3.0)) 
                       
            current_count = review_elements.count()
            
            # 스크롤을 내렸는데도 리뷰 개수가 아까랑 똑같다면?
            if current_count == previous_count:
                retry_count += 1
                print(f"새로운 리뷰 로딩을 기다리는 중... (재시도 {retry_count}/3)")
                
                # 3번이나 기다렸는데도 안 늘어나면 진짜 끝까지 다 본 걸로 판단!
                if retry_count >= 3: 
                    print("더 이상 불러올 리뷰가 없는 것 같아서 스크롤을 멈출게!")
                    break
            else:
                retry_count = 0 # 새 리뷰가 나타났으면 인내심 카운터 다시 초기화!

        # 4. 데이터 추출 (6가지 필드)
        count_to_extract = min(target_count, review_elements.count())
        for i in range(count_to_extract):
            box = review_elements.nth(i)
            
            # 💡 [핵심 수정] 데이터를 뽑기 직전에 스포일러가 있는지 확인하고 열어주기!
            try:
                # 박스 안에 "스포일러가 있어요!!" 문구가 들어있다면?
                if box.locator('text="스포일러가 있어요!!"').count() > 0:
                    # 핑크색 "보기" 글자를 정확하게 찾아서 콕! 클릭
                    box.get_by_text("보기", exact=True).click()
                    time.sleep(0.5) # 숨겨진 리뷰가 짠! 하고 나타날 때까지 0.5초만 여유 주기
            except Exception as e:
                pass # 혹시 클릭 안 되더라도 에러 없이 부드럽게 다음으로 넘어가기!

            try:
                all_reviews_data.append({
                    "리뷰어_닉네임": box.locator("._userName_1cqxl_29").inner_text(),
                    "별점": box.locator("._rating_1cqxl_68 p").inner_text() if box.locator("._rating_1cqxl_68 p").count() > 0 else "없음",
                    "좋아요_수": box.locator('button:has-text("좋아요") span').inner_text() if box.locator('button:has-text("좋아요") span').count() > 0 else "0",
                    "댓글_수": box.locator('button:has-text("댓글") span').inner_text() if box.locator('button:has-text("댓글") span').count() > 0 else "0",
                    "영화_제목": movie_title,
                    # 스포일러가 풀렸으니 이제 진짜 본문이 예쁘게 담길 거야!
                    "리뷰_본문_내용": box.locator(".CommentText").inner_text()
                })
            except: continue

    # 6. JSON 데이터 저장
    os.makedirs("data", exist_ok=True)
    file_path = f"data/{movie_title}_리뷰.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(all_reviews_data, f, ensure_ascii=False, indent=4)
    
    print(f"\n✅ 저장 완료! 총 {len(all_reviews_data)}개의 리뷰를 챙겼어.")

def main():
    # 사용자가 원하는 영화와 수집 분포 입력
   
    # 7. 전체 실행 흐름
    # (1) 페이지 접속 및 로그인 (기존 함수 활용)
    page = go_to_movie_comments(MOVIE)
    
    # (2) 리뷰 수집 진행
    scrape_reviews(page, MOVIE, distribution_input)
    
    # (3) 모든 작업이 끝나면 브라우저 닫기
    print("🚀 모든 임무 완료! 브라우저를 닫을게.")
    page.context.browser.close()

if __name__ == "__main__":
    main()