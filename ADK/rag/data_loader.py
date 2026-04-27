import json
import os
from langchain_core.documents import Document

class MovieDataLoader:
    def __init__(self, file_path):
        self.file_path = file_path

    def load_documents(self):
        """JSON 파일을 읽어 LangChain Document 리스트로 변환합니다."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {self.file_path}")

        with open(self.file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        movie_info = data.get("영화_정보", {})
        reviews = data.get("리뷰_목록", [])

        documents = []
        for review in reviews:
            # 메타데이터 구성 (Self-Querying을 위해 명확한 타입 변환)
            metadata = {
                "movieNm": movie_info.get("movieNm", "Unknown"),
                "openDt": movie_info.get("openDt", ""),
                "genreAlt": movie_info.get("genreAlt", ""),
                "rating": float(review.get("별점", 0.0)) if review.get("별점") else 0.0,
                "likes": int(review.get("좋아요_수", 0)) if review.get("좋아요_수") else 0
            }
            
            # 리뷰 본문을 페이지 내용으로 설정
            page_content = review.get("리뷰_본문_내용", "")
            if page_content:
                documents.append(Document(page_content=page_content, metadata=metadata))
        
        return documents
