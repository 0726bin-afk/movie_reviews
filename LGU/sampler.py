import json
import random
import os
import ollama

LGU_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(LGU_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
target_path = os.path.join(DATA_DIR, "cleaned_total_reviews.json")
output_path = os.path.join(DATA_DIR, "test_reviews_sample.json")
LOCAL_MODEL = "gemma4"

with open(target_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

all_reviews = []
for movie, content in data.items():
    revs = content.get('reviews', [])
    all_reviews.extend(revs)

# 기본적인 필터링 그룹
pos_reviews = [r for r in all_reviews if r.get('rating', 0) >= 4.0]
neu_reviews = [r for r in all_reviews if 2.5 <= r.get('rating', 0) <= 3.5]
neg_reviews = [r for r in all_reviews if r.get('rating', 0) <= 2.0]
spoiler_reviews = [r for r in all_reviews if r.get('is_spoiler')]

random.seed(42)
random.shuffle(pos_reviews)
random.shuffle(neu_reviews)
random.shuffle(neg_reviews)
random.shuffle(spoiler_reviews)

def llm_filter(reviews, target_count, category_name):
    """LLM을 이용해 분류 모델 테스트에 적합한 수작업 양질의 리뷰만 추출합니다."""
    print(f"🤖 LLM({LOCAL_MODEL}) 필터링 시작 - {category_name} ({target_count}개 목표)")
    extracted = []
    
    for r in reviews:
        if len(extracted) >= target_count:
            break
        
        text = r.get('content', '')
        if len(text) < 10 or len(text) > 600:
            continue
            
        prompt = f"""
        당신은 AI 학습 데이터 구축 전문가입니다. 다음 리뷰 문장이 영화 감성 분석 및 특징(연출, 연기, 스토리 등) 분류 모델을 테스트하기 위한 '양질의 테스트 데이터'인지 판단하세요.
        문맥이 명확하고 단순한 욕설이나 의미 없는 나열이 아닌 경우 '적합'을, 그렇지 않으면 '부적합'을 출력하세요.
        다른 부가 설명 없이 오직 [적합] 또는 [부적합] 이라는 단어만 대답하세요.
        
        리뷰 문장: {text}
        """
        try:
            response = ollama.chat(model=LOCAL_MODEL, messages=[{'role': 'user', 'content': prompt}])
            result = response['message']['content'].strip()
            
            if "적합" in result and "부적합" not in result:
                extracted.append(r)
                print(f" ✅ [적합] ({len(extracted)}/{target_count}) {text[:30]}...")
            else:
                pass # 부적합 패스
        except Exception as e:
            print(f" ⚠️ LLM 에러: {e}")
            
    return extracted

unique_sample = []
# 각각 LLM을 통해 정예 리뷰만 추출
unique_sample.extend(llm_filter(pos_reviews, 30, "긍정적 리뷰"))
unique_sample.extend(llm_filter(neu_reviews, 20, "중립/모호한 리뷰"))
unique_sample.extend(llm_filter(neg_reviews, 20, "부정적 리뷰"))
unique_sample.extend(llm_filter(spoiler_reviews, 15, "스포일러 리뷰"))

# 중복 제거
seen = set()
final_sample = []
for r in unique_sample:
    if r['review_id'] not in seen:
        seen.add(r['review_id'])
        final_sample.append(r)

with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(final_sample, f, ensure_ascii=False, indent=4)

print("="*50)
print(f"Total {len(final_sample)} reviews uniquely extracted using LLM ({LOCAL_MODEL}).")
print(f"Saved at: {output_path}")
