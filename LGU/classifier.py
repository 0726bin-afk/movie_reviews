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

# 🏷️ 백업용 키워드 사전 (LLM 실패 시 사용)
TAG_RULES = {
    "연기": ["배우", "연기", "열연", "캐릭터", "몰입감"],
    "연출": ["연출", "감독", "카메라", "구도", "화면"],
    "서사": ["스토리", "전개", "각본", "극본", "줄거리"],
    "분위기": ["분위기", "감성", "무드", "느낌"],
    "주의사항": ["노출", "가족", "민망", "야한", "잔인", "공포", "폭력"]
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

def classify_batch_with_local_llm(review_batch):
    """로컬 Ollama를 사용하여 여러 개의 리뷰를 한 번에 분석하는 함수"""
    batch_text = ""
    for idx, r in enumerate(review_batch):
        batch_text += f"ID:{idx} | 본문: {r['content']}\n"

    prompt = f"""
    당신은 영화 리뷰 분석 전문가입니다. 다음 {len(review_batch)}개의 리뷰를 각각 분석하여 정보를 추출하세요.
    응답은 반드시 한국어로 작성하세요.

    [범주]: 연기, 연출, 서사, 비주얼, 음악, 분위기, 고증, 주의사항, TMI, 장르특성, 평가
    
    [응답 지시]:
    각 리뷰의 ID별로 아래 JSON 구조를 가지는 리스트로 답변하세요.
    - content_character: 해당하는 범주 리스트
    - search_keywords: 대표 키워드 최대 3개

    [리뷰 리스트]:
    {batch_text}

    반드시 마크다운 코드 블록 없이 순수한 JSON 리스트 형식으로만 응답하세요:
    [
        {{"id": 0, "content_character": [], "search_keywords": []}},
        ...
    ]
    """

    try:
        response = ollama.chat(model=LOCAL_MODEL, messages=[
            {'role': 'user', 'content': prompt},
        ])
        
        response_text = response['message']['content']
        # JSON 문자열만 추출 (마크다운 코드 블록 등 제거)
        json_text = re.sub(r'```json|```', '', response_text).strip()
        results = json.loads(json_text)
        return sorted(results, key=lambda x: x['id'])
    except Exception as e:
        print(f"⚠️ 로컬 LLM 분석 중 오류 발생: {e}")
        return None

def run_classification():
    input_path = os.path.join(DATA_DIR, "cleaned_total_reviews.json")
    output_path = os.path.join(DATA_DIR, "tagged_reviews.json")

    if not os.path.exists(input_path):
        print(f"❌ '{input_path}' 파일이 없습니다. 먼저 cleaner.py를 실행해 주세요.")
        return

    # 기존 작업 결과 불러오기 (이어하기)
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print("📝 기존 작업 결과에서 이어하기를 시작합니다.")
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    pending_reviews = []
    for m_name, m_data in data.items():
        for rev in m_data.get("reviews", []):
            if rev.get("meta_tags", {}).get("analysis_method") != "Local-LLM":
                pending_reviews.append(rev)

    if not pending_reviews:
        print("✅ 모든 리뷰에 대한 분석이 이미 완료되었습니다.")
        return

    print(f"🚀 총 {len(pending_reviews)}개의 리뷰를 로컬 LLM({LOCAL_MODEL})으로 분석합니다.")
    
    batch_size = 10 # 로컬 성능에 따라 조절 가능
    for i in range(0, len(pending_reviews), batch_size):
        current_batch = pending_reviews[i:i+batch_size]
        print(f"📦 배치 분석 중... ({i}/{len(pending_reviews)})")
        
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
        
        # 중간 저장
        if (i // batch_size) % 3 == 0:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    # 최종 저장
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"\n✨ 로컬 LLM 분석 완료! 결과 저장: {output_path}")

if __name__ == "__main__":
    run_classification()
