from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.retrievers.self_query.base import SelfQueryRetriever
from langchain_classic.chains.query_constructor.schema import AttributeInfo

class RetrieverBuilder:
    def __init__(self):
        # 사용자가 요청한 gemini-3-flash-preview 모델 사용 (또는 최신 지원 모델)
        self.llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0)

    def build_self_query_retriever(self, vector_store):
        """메타데이터 필터링이 가능한 Self-Querying Retriever를 구축합니다."""
        
        # 메타데이터 필드 정의
        metadata_field_info = [
            AttributeInfo(
                name="movieNm",
                description="The name of the movie",
                type="string",
            ),
            AttributeInfo(
                name="openDt",
                description="The release date of the movie (YYYY-MM-DD)",
                type="string",
            ),
            AttributeInfo(
                name="genreAlt",
                description="The genres of the movie (comma separated)",
                type="string",
            ),
            AttributeInfo(
                name="rating",
                description="The star rating given by the reviewer (0.0 to 5.0)",
                type="float",
            ),
            AttributeInfo(
                name="likes",
                description="The number of likes the review received",
                type="integer",
            ),
        ]
        
        document_content_description = "Reviews and fan comments for various movies"
        
        # Self-Querying Retriever 생성
        retriever = SelfQueryRetriever.from_llm(
            llm=self.llm,
            vectorstore=vector_store,
            document_contents=document_content_description,
            metadata_field_info=metadata_field_info,
            verbose=True
        )
        
        return retriever
