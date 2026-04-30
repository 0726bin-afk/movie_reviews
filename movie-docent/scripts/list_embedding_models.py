"""
현재 GEMINI_API_KEY로 호출 가능한 임베딩 모델 목록 출력.

실행:
    python scripts/list_embedding_models.py

API 키가 어떤 모델에 접근 가능한지 빠르게 확인.
404 에러 디버깅 시 사용.
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        # .env가 있으면 로드 시도
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("GEMINI_API_KEY")
        except ImportError:
            pass

    if not api_key:
        print("❌ GEMINI_API_KEY 환경변수 없음. .env 설정 후 재시도.")
        sys.exit(1)

    try:
        import google.generativeai as genai
    except ImportError:
        print("❌ google-generativeai 미설치: pip install google-generativeai")
        sys.exit(1)

    genai.configure(api_key=api_key)

    print("=== embedContent 지원 모델 ===")
    found = 0
    for m in genai.list_models():
        if "embedContent" in (m.supported_generation_methods or []):
            print(f"  • {m.name}")
            print(f"      display: {m.display_name}")
            print(f"      input limit: {m.input_token_limit}")
            print(f"      output dim:  {getattr(m, 'output_dimensionality', '?')}")
            print()
            found += 1

    if found == 0:
        print("⚠️  embedContent 지원 모델 0건. 키 권한 또는 region 확인.")
    else:
        print(f"총 {found}개 모델 사용 가능.")


if __name__ == "__main__":
    main()
