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

# 🏷️ 백업용 키워드 사전 (LLM 실패 시 사용)
TAG_RULES = {
    "연기좋음": ["열연", "명연기", "연기력", "인생 캐릭터", "소름", "연기 잘"],
    "연기나쁨": ["연기력 논란", "발연기", "어색", "몰입 방해", "연기 못"],
    "연출좋음": ["영상미", "미장센", "감각적", "탁월한 연출", "연출력"],
    "연출나쁨": ["조잡", "촌스러운", "연출력 부족", "엉성한 연출"],
    "서사좋음": ["탄탄한", "짜임새", "명작", "완벽한 서사", "개연성"],
    "서사나쁨": ["지루", "뻔한", "용두사미", "허술", "개연성 부족"],
    "비주얼좋음": ["비주얼", "영상미", "눈이 즐거운", "그래픽", "훌륭한 CG"],
    "비주얼나쁨": ["허접한 CG", "촌스러운 비주얼", "어색한 그래픽"],
    "음악좋음": ["ost", "음악", "사운드트랙", "배경음악", "음악이 좋"],
    "음악나쁨": ["음악이 안 어울", "시끄러운", "음악이 별로"],
    "분위기가벼움": ["가벼운 분위기", "유쾌한", "밝은 분위기", "경쾌한"],
    "분위기무거움": ["산만한 분위기", "분위기 깨는", "칙칙한", "어두운 분위기", "진지한"],
    "고증좋음": ["고증이 잘 된", "현실적인", "디테일"],
    "고증나쁨": ["고증 오류", "비현실적인"],
    "주의사항": ["노출", "가족", "민망", "야한", "잔인", "공포", "폭력"],
    "전체긍정": ["최고", "추천", "재밌", "훌륭", "완벽", "인생 영화", "강추"],
    "전체부정": ["최악", "비추", "노잼", "별로", "시간 아깝", "실망", "돈 아깝"]
}

def classify_with_rule_base(content):
    found_tags = []
    extracted_keywords = []
    for tag_name, keywords in TAG_RULES.items():
        matched = [k for k in keywords if k in content]
        if matched:
            found_tags.append(tag_name)
            extracted_keywords.extend(matched)
    if not found_tags: found_tags.append("일반감상")
    return found_tags, list(set(extracted_keywords))

def classify_batch_with_local_llm(review_batch, max_retries=5):
    """로컬 Ollama를 사용하여 여러 개의 리뷰를 한 번에 분석하는 함수"""
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
    for attempt in range(max_retries):
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
            print(f"⚠️ 로컬 LLM 분석 오류 또는 품질 미달 (시도 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2) # 잠시 대기 후 재시도 (대기 시간 증가)
            else:
                print("❌ 최대 재시도 횟수 초과. Fallback(Rule-based)으로 넘어갑니다.")
                return None

def run_classification():
    input_path = os.path.join(DATA_DIR, "cleaned_total_reviews.json")
    
    if IS_TEST_MODE:
        output_path = os.path.join(DATA_DIR, "test_tagged_reviews.json")
    else:
        output_path = os.path.join(DATA_DIR, "tagged_reviews.json")

    if not os.path.exists(input_path):
        print(f"❌ '{input_path}' 파일이 없습니다. 경로를 확인해 주세요.")
        return
    else:
        # 1. 항상 원본 데이터(전체)를 베이스로 불러옵니다.
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 2. 기존 작업 결과가 있다면 불러와서 덮어씌웁니다 (이어하기)
        if os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                processed_data = json.load(f)
            print("📝 기존 작업 결과에서 이어하기를 시작합니다.")

            for m_name, m_data in processed_data.items():
                if m_name in data:
                    processed_reviews_dict = {r.get("review_id"): r for r in m_data.get("reviews", [])}
                    for i, rev in enumerate(data[m_name].get("reviews", [])):
                        if rev.get("review_id") in processed_reviews_dict:
                            data[m_name]["reviews"][i] = processed_reviews_dict[rev["review_id"]]

    pending_reviews = []
    for m_name, m_data in data.items():
        for rev in m_data.get("reviews", []):
            if rev.get("meta_tags", {}).get("analysis_method") not in ["Local-LLM", "Rule-based (Fallback)"]:
                pending_reviews.append(rev)

    if not pending_reviews:
        print("✅ 모든 리뷰에 대한 분석이 이미 완료되었습니다.")
    else:
        # 테스트 모드 적용
        if IS_TEST_MODE:
            pending_reviews = pending_reviews[:TEST_LIMIT]
            print(f"⚠️ [테스트 모드 활성화] 리뷰 수를 {len(pending_reviews)}개로 제한하여 분석합니다.")

        print(f"🚀 총 {len(pending_reviews)}개의 리뷰를 로컬 LLM({LOCAL_MODEL})으로 분석합니다.")

        batch_size = 1 # 절대적인 안정성을 위해 1개씩 처리
        import time, datetime
        start_time = time.time()
        
        for i in range(0, len(pending_reviews), batch_size):
            current_batch = pending_reviews[i:i+batch_size]
            percentage = (i / len(pending_reviews)) * 100
            
            elapsed = time.time() - start_time
            if i > 0:
                eta_seconds = (elapsed / i) * (len(pending_reviews) - i)
                eta_str = str(datetime.timedelta(seconds=int(eta_seconds)))
            else:
                eta_str = "계산 중..."
                
            elapsed_str = str(datetime.timedelta(seconds=int(elapsed)))
            print(f"📦 분석 중... ({i}/{len(pending_reviews)} - {percentage:.1f}%) | 소요: {elapsed_str} | 남은시간: {eta_str}")

            results = classify_batch_with_local_llm(current_batch)

            if results and len(results) == len(current_batch):
                for idx, res in enumerate(results):
                    rev = current_batch[idx]
                    rev["meta_tags"].update({
                        "content_character": res.get("content_character", []),
                        "search_keywords": res.get("search_keywords", []),
                        "is_tmi": "TMI" in res.get("content_character", []),
                        "has_warning": "주의사항" in res.get("content_character", []),
                        "analysis_method": "Local-LLM"
                    })
            else:
                print("⚠️ 일부 배치 분석 실패. 키워드 매칭으로 대체합니다.")
                for rev in current_batch:
                    tags, keywords = classify_with_rule_base(rev["content"])
                    rev["meta_tags"].update({
                        "content_character": tags,
                        "search_keywords": keywords,
                        "analysis_method": "Rule-based (Fallback)"
                    })

            # 중간 저장 (분석이 완료된 리뷰만 필터링하여 출력)
            if (i // batch_size) % 3 == 0:
                filtered_data = {}
                for m_name, m_data in data.items():
                    processed_reviews = [r for r in m_data.get("reviews", []) if r.get("meta_tags", {}).get("analysis_method") in ("Local-LLM", "Rule-based (Fallback)")]
                    if processed_reviews:
                        filtered_data[m_name] = {"movie_metadata": m_data.get("movie_metadata", {}), "reviews": processed_reviews}
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(filtered_data, f, ensure_ascii=False, indent=4)

        # 최종 저장 (분석이 완료된 리뷰만 필터링하여 출력)
        filtered_data = {}
        for m_name, m_data in data.items():
            processed_reviews = [r for r in m_data.get("reviews", []) if r.get("meta_tags", {}).get("analysis_method") in ("Local-LLM", "Rule-based (Fallback)")]
            if processed_reviews:
                filtered_data[m_name] = {"movie_metadata": m_data.get("movie_metadata", {}), "reviews": processed_reviews}

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(filtered_data, f, ensure_ascii=False, indent=4)

        print(f"\n✨ 로컬 LLM 분석 완료! 결과 저장: {output_path}")

if __name__ == "__main__":
    run_classification()
