import os
from dotenv import load_dotenv
from data_loader import MovieDataLoader
from vector_service import VectorService
from retriever_builder import RetrieverBuilder
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI

# .env 파일에서 환경 변수 로드
load_dotenv()

def run_movie_docent(json_file_path, query):
    # 1. 데이터 로드 및 전처리
    print("--- 1단계: 데이터 로딩 중 ---")
    loader = MovieDataLoader(json_file_path)
    docs = loader.load_documents()
    print(f"로딩 완료: {len(docs)}개의 리뷰 문서를 찾았습니다.")

    # 2. 벡터 저장소 구성 및 문서 저장
    print("\n--- 2단계: 벡터 DB 저장 중 (Batch 처리) ---")
    v_service = VectorService(persist_directory="./movie_docent_db")
    vector_store = v_service.save_documents_in_batches(docs)

    # 3. Retriever 구축 (Self-Querying)
    print("\n--- 3단계: Self-Querying Retriever 구축 중 ---")
    r_builder = RetrieverBuilder()
    retriever = r_builder.build_self_query_retriever(vector_store)

    # 4. LLM 및 프롬프트 설정 (LCEL 체인 구성)
    print("\n--- 4단계: LCEL 체인 실행 중 ---")
    model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.2)
    
    template = """
    당신은 영화 전문 도슨트입니다. 제공된 리뷰 정보를 바탕으로 사용자의 질문에 친절하고 상세하게 답변해주세요.
    검색된 리뷰에 영화 정보(제목, 장르, 개봉일)가 포함되어 있다면 이를 활용하세요.
    
    # 검색된 리뷰 정보:
    {context}
    
    # 사용자 질문:
    {question}
    
    # 답변 가이드:
    - 리뷰의 전반적인 분위기와 핵심 내용을 요약해주세요.
    - 가능한 경우 구체적인 별점이나 좋아요 수를 언급하여 신뢰도를 높이세요.
    - 도슨트처럼 우아하고 전문적인 말투를 사용하세요.
    """
    prompt = ChatPromptTemplate.from_template(template)

    # LCEL 체인 정의: retriever | prompt | model | parser
    chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | model
        | StrOutputParser()
    )

    # 5. 실행
    response = chain.invoke(query)
    return response

if __name__ == "__main__":
    # 실행 예시 (실제 파일 경로와 질문으로 변경 가능)
    sample_file = "./data/트루먼 쇼_리뷰.json"
    user_query = "별점이 4.0 이상인 리뷰들 중에서 트루먼 쇼의 핵심 감상평을 정리해줘."
    
    if os.path.exists(sample_file):
        result = run_movie_docent(sample_file, user_query)
        print("\n[지능형 영화 도슨트 답변]")
        print("-" * 50)
        print(result)
        print("-" * 50)
    else:
        print(f"파일을 찾을 수 없습니다: {sample_file}. 경로를 확인해주세요.")
