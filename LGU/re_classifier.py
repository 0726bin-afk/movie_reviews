import json
import os
import time
import re
import ollama  # 로컬 LLM 제어용 라이브러리
from dotenv import load_dotenv

# 🏗️ 설정 및 경로 로드 (프로젝트 루트 기준)
LGU_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(LGU_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")

# .env 파일 로드 (루트 폴더)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

# 로컬 LLM 설정 (Ollama)
# 미리 'ollama pull gemma4' 명령어로 모델을 다운로드 받아야 합니다.
LOCAL_MODEL = "gemma4"

# 🚀 테스트 모드 스위치 (개발 및 빠른 테스트용)
IS_TEST_MODE = False  # True로 설정 시 전체가 아닌 일부 리뷰만 제한적으로 분석합니다.
TEST_LIMIT = 20       # 테스트 모드 시 분석할 최대 리뷰 개수

def classify_batch_with_local_llm(review_batch):
    """로컬 Ollama를 사용하여 여러 개의 리뷰를 한 번에 분석하는 함수 (성공할 때까지 무한 재시도)"""
    batch_text = ""
    for idx, r in enumerate(review_batch):
        batch_text += f"ID:{idx} | 본문: {r['content']}\n"

    prompt = f"""
    당신은 영화 리뷰 분석 전문가입니다. 다음 {len(review_batch)}개의 리뷰를 각각 분석하여 정보를 추출하세요.
    응답은 반드시 한국어로 작성하세요.

    [범주]: 전체긍정, 전체부정, 전체복합, 연기좋음, 연기나쁨, 연출좋음, 연출나쁨, 서사좋음, 서사나쁨, 비주얼좋음, 비주얼나쁨, 음악좋음, 분위기가벼움, 분위기무거움, 고증좋음, 고증나쁨, 주의사항, TMI, 장르특성

    [분석 지침]:
    - 각 리뷰의 본문을 꼼꼼히 읽고 해당되는 모든 범주를 선택하세요.
    - 가장 먼저 리뷰의 전체적인 총평이나 분위기가 긍정적이면 '전체긍정', 부정적이면 '전체부정', 장단점이 섞여있거나 모호하면 '전체복합' 중 하나를 반드시 포함하세요.
    - 특히 '연기', '연출', '서사', '비주얼', '음악', '분위기'는 단순히 내용 언급이 아니라, 긍정적인 평가면 '좋음', 부정적인 평가면 '나쁨'을 붙여서 상세히 태깅하세요.
    - ⚠️ 절대 비워두지 마세요: 모든 리뷰에 대해 반드시 최소 1개 이상의 'content_character'를 찾아야 합니다.
    - ⚠️ 절대 비워두지 마세요: 'search_keywords'는 본문 내용에서 유추할 수 있는 대표 핵심 단어를 개수 제한 없이 최대한 다양하고 풍부하게 추출하세요 (최소 1개 이상).

    [응답 지시 (매우 중요)]:
    1. 반드시 아래 제시된 단일 JSON 객체 형식으로만 응답해야 합니다. 리스트나 다른 부가적인 텍스트는 절대 포함하지 마세요.
    2. JSON 문법을 완벽하게 지켜야 합니다. 키와 값은 반드시 큰따옴표(")로 감싸야 하며, 문자열 내부에 큰따옴표가 들어갈 경우 작은따옴표(')로 대체하세요.
    3. 항목 사이의 쉼표(,)를 절대 누락하지 마세요.
    4. 제공된 리뷰에 대한 분석 결과를 단일 JSON 객체로 응답하세요.

    형식 예시 (실제 값으로 대체할 것):
    {{
        "id": 0,
        "content_character": ["추출한태그1", "추출한태그2"],
        "search_keywords": ["핵심단어1", "핵심단어2", "핵심단어3"]
    }}

    [리뷰 리스트]:
    {batch_text}
    """

    import time
    attempt = 0
    while True:
        attempt += 1
        try:
            response = ollama.chat(model=LOCAL_MODEL, messages=[
                {'role': 'user', 'content': prompt},
            ], format='json')

            response_text = response['message']['content']
            # 마크다운 블록 제거 및 텍스트 정리
            json_text = re.sub(r'```json|```', '', response_text).strip()

            result_obj = json.loads(json_text)
            
            # 단일 딕셔너리 응답일 경우 리스트로 감싸줌
            if isinstance(result_obj, dict):
                results = [result_obj]
            else:
                results = result_obj

            # 검증 1: 결과 개수가 맞는지 확인
            if len(results) != len(review_batch):
                raise ValueError(f"응답 개수 불일치 (요청: {len(review_batch)}개, 응답: {len(results)}개)")

            # 검증 2: 빈 배열 및 꼼수(프롬프트 복사) 확인
            for res in results:
                content_chars = res.get("content_character", [])
                keywords = res.get("search_keywords", [])

                if not content_chars or not keywords:
                    raise ValueError(f"ID {res.get('id')}의 태그나 키워드가 비어있습니다. 재생성을 요구합니다.")

                # 허용되지 않은 태그 필터링 (품질 보장)
                allowed_tags = {"전체긍정", "전체부정", "전체복합", "연기좋음", "연기나쁨", "연출좋음", "연출나쁨", "서사좋음", "서사나쁨", "비주얼좋음", "비주얼나쁨", "음악좋음", "분위기가벼움", "분위기무거움", "고증좋음", "고증나쁨", "주의사항", "TMI", "장르특성"}
                res["content_character"] = [t for t in content_chars if t in allowed_tags]
                
                # 만약 필터링 후 태그가 다 날아갔다면 기본값
                if not res["content_character"]:
                    res["content_character"] = ["일반감상"]

                # 프롬프트 예시를 그대로 복사했는지 검증
                if "추출한태그1" in content_chars or "핵심단어1" in keywords:
                    raise ValueError(f"ID {res.get('id')}가 예시를 그대로 복사했습니다. 재분석 요구.")

                # 리뷰 원본을 찾아서 길이가 긴데 태그가 부실한지 체크
                original_review = next((r for idx, r in enumerate(review_batch) if idx == res['id']), None)
                if original_review and len(original_review['content']) > 100:
                    if len(content_chars) < 2:
                        raise ValueError(f"ID {res.get('id')}는 100자 이상 리뷰인데 태그가 부족합니다({content_chars}). 재분석 요구.")

            return sorted(results, key=lambda x: x['id'])
        except Exception as e:
            print(f"⚠️ 로컬 LLM 분석 오류 또는 품질 미달 (시도 {attempt}): {e}")
            time.sleep(2) # 잠시 대기 후 무한 재시도

def run_re_classification():
    target_path = os.path.join(DATA_DIR, "tagged_reviews.json")

    if not os.path.exists(target_path):
        print(f"❌ '{target_path}' 파일이 없습니다. 먼저 classifier.py를 통해 리뷰 분석을 진행해 주세요.")
        return

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pending_reviews = []
    # 원본 데이터 객체에 바로 업데이트하기 위해 위치(인덱스)를 저장
    pending_refs = [] 

    # 룰베이스(Rule-based)로 태깅된 리뷰만 필터링
    for m_name, m_data in data.items():
        for i, rev in enumerate(m_data.get("reviews", [])):
            method = rev.get("meta_tags", {}).get("analysis_method", "")
            if method == "Rule-based (Fallback)":
                pending_reviews.append(rev)
                pending_refs.append((m_name, i))

    if not pending_reviews:
        print("✅ 룰베이스로 분류된 리뷰가 없습니다! 모든 리뷰가 LLM으로 정상 분류되었습니다.")
        return

    # 테스트 모드 적용
    if IS_TEST_MODE:
        pending_reviews = pending_reviews[:TEST_LIMIT]
        pending_refs = pending_refs[:TEST_LIMIT]
        print(f"⚠️ [테스트 모드 활성화] 리뷰 수를 {len(pending_reviews)}개로 제한하여 재분석합니다.")

    print(f"🚀 총 {len(pending_reviews)}개의 룰베이스 처리된 리뷰를 로컬 LLM({LOCAL_MODEL})으로 재분석합니다.")

    batch_size = 1 # 절대적인 안정성을 위해 1개씩 처리
    success_count = 0
    import time, datetime
    start_time = time.time()

    for i in range(0, len(pending_reviews), batch_size):
        current_batch = pending_reviews[i:i+batch_size]
        current_refs = pending_refs[i:i+batch_size]
        percentage = (i / len(pending_reviews)) * 100
        
        elapsed = time.time() - start_time
        if i > 0:
            eta_seconds = (elapsed / i) * (len(pending_reviews) - i)
            eta_str = str(datetime.timedelta(seconds=int(eta_seconds)))
        else:
            eta_str = "계산 중..."
            
        elapsed_str = str(datetime.timedelta(seconds=int(elapsed)))
        print(f"📦 재분석 중... ({i}/{len(pending_reviews)} - {percentage:.1f}%) | 소요: {elapsed_str} | 남은시간: {eta_str}")

        results = classify_batch_with_local_llm(current_batch)

        for idx, res in enumerate(results):
            m_name, rev_idx = current_refs[idx]
            
            # 원본 데이터 구조 바로 수정
            data[m_name]["reviews"][rev_idx]["meta_tags"].update({
                "content_character": res.get("content_character", []),
                "search_keywords": res.get("search_keywords", []),
                "is_tmi": "TMI" in res.get("content_character", []),
                "has_warning": "주의사항" in res.get("content_character", []),
                "analysis_method": "Local-LLM"
            })
            success_count += 1

        # 중간 저장
        if (i // batch_size) % 3 == 0:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    # 최종 저장
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"\n✨ 재분석 완료! (성공하여 덮어쓴 리뷰: {success_count}개)")
    print(f"결과 저장: {target_path}")

if __name__ == "__main__":
    run_re_classification()
