import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

class VectorService:
    def __init__(self, persist_directory="./chroma_db"):
        # Google Generative AI Embeddings 설정
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001"
        )
        self.persist_directory = persist_directory

    def save_documents_in_batches(self, documents, batch_size=250):
        """문서를 batch_size만큼 묶어서 Vector Store에 저장 (API 효율 최적화)"""
        # 기존 DB 로드 또는 새로 생성
        vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings
        )
        
        # Batch 처리 (최대 250개씩)
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            vector_store.add_documents(batch)
            print(f"Batch {i//batch_size + 1} 처리 완료: {len(batch)}개 문서 추가됨.")
        
        return vector_store

    def load_vector_store(self):
        """저장된 벡터 스토어를 로드합니다."""
        return Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings
        )
