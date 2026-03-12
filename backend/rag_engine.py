"""
RAG 엔진 — 하이브리드 검색 + 출처 표시 + 할루시네이션 방지
기존 rag_pipeline.py를 프로덕션 수준으로 리팩토링한 모듈입니다.
"""

import os
import json
import sys
from typing import List, Dict, Any, Optional

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_community.retrievers import BM25Retriever

# 프로젝트 루트
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ChromaDB 영속 저장 경로
CHROMA_PERSIST_DIR = os.path.join(PROJECT_ROOT, "data", "chromadb")

# 시스템 프롬프트 — 출처 표시 + 할루시네이션 방지
SYSTEM_PROMPT = """당신은 세종대학교 학사 정보 AI 어시스턴트 'SejongBrain'입니다.

## 핵심 규칙
1. **반드시 아래 Context에 있는 정보만 사용**하여 답변하세요.
2. Context에 없는 내용은 "제공된 문서에서 해당 정보를 찾지 못했습니다. 학교 홈페이지나 학사지원팀에 문의해 주세요."라고 답변하세요.
3. 답변 끝에 반드시 **📎 출처** 섹션을 추가하고, 참고한 문서의 제목과 페이지를 표시하세요.
4. 학칙 조항 번호가 있으면 정확히 인용하세요.
5. 한국어로 답변하되, 존댓말을 사용하세요.
6. 답변은 간결하고 핵심 위주로 작성하세요.

## Context
{context}

## 질문
{question}
"""

# 상위 청크 개수
TOP_K = 15


class RAGEngine:
    """SejongBrain RAG 검색 엔진"""

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        embedding_model: str = "gemini-embedding-001",
        llm_model: str = "gemini-2.5-flash",
        persist_dir: str = CHROMA_PERSIST_DIR,
    ):
        # API 키 설정
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key
        elif not os.environ.get("GOOGLE_API_KEY"):
            config_path = os.path.join(PROJECT_ROOT, "config.json")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = json.load(f)
                os.environ["GOOGLE_API_KEY"] = config["GOOGLE_API_KEY"]

        self.persist_dir = persist_dir
        
        # Jina 임베딩 모델 로드 (trust_remote_code=True 필수)
        print("🔄 Jina Embedding 모델을 로드하는 중입니다 (첫 실행 시 다운로드 소요)...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="jinaai/jina-embeddings-v5-text-small",
            model_kwargs={'trust_remote_code': True},
            encode_kwargs={'task': 'retrieval'}
        )
        
        self.llm = ChatGoogleGenerativeAI(model=llm_model, temperature=0)
        self.vectorstore = None
        self.bm25_retriever = None
        self.all_chunks = []
        self.rag_chain = None

    def index_documents(self, chunks: List[Document], batch_size: int = 4):
        """청크를 벡터 DB에 배치로 나누어 인덱싱합니다 (레이트 리밋 대응 + 중복 방지)."""
        import time
        
        print(f"📦 {len(chunks)}개 청크 검토 중 (배치 크기: {batch_size})...")
        os.makedirs(self.persist_dir, exist_ok=True)

        existing_ids = set()
        # 기존 인덱스가 있으면 로드하여 이미 있는 ID(출처+인덱스)를 추출
        if os.path.exists(self.persist_dir):
            try:
                if not self.vectorstore:
                    self.vectorstore = Chroma(
                        persist_directory=self.persist_dir,
                        embedding_function=self.embeddings,
                        collection_name="sejong_brain_jina_v5",
                    )
                all_data = self.vectorstore.get()
                if all_data and all_data.get("ids"):
                    existing_ids = set(all_data["ids"])
            except Exception as e:
                print(f"   ⚠️ 기존 DB 접근 실패 (새로 생성합니다): {e}")

        new_chunks = []
        new_ids = []
        seen_in_batch = set()
        
        for chunk in chunks:
            src = chunk.metadata.get("source", "unknown")
            page = chunk.metadata.get("page_number", 0)
            idx = chunk.metadata.get("chunk_index", 0)
            chunk_id = f"{src}::p{page}::i{idx}"
            
            # DB에도 없고, 현재 추가할 목록에도 중복되지 않은 경우만
            if chunk_id not in existing_ids and chunk_id not in seen_in_batch:
                new_chunks.append(chunk)
                new_ids.append(chunk_id)
                seen_in_batch.add(chunk_id)

        if not new_chunks:
            print("📦 모든 문서가 이미 인덱싱되어 있습니다. 생략합니다.")
            self.all_chunks = chunks
            self._build_chain()
            return

        print(f"📦 추가할 새로운 청크 {len(new_chunks)}개 발견! 벡터 DB에 인덱싱합니다...")

        # 50개 단위 배치 처리
        total_batches = (len(new_chunks) - 1) // batch_size + 1
        for i in range(0, len(new_chunks), batch_size):
            batch_chunks = new_chunks[i:i + batch_size]
            batch_ids = new_ids[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            for attempt in range(3):
                try:
                    if self.vectorstore is None:
                        # 아직 vectorstore가 초기화되지 않았다면 생성
                        self.vectorstore = Chroma.from_documents(
                            documents=batch_chunks,
                            embedding=self.embeddings,
                            ids=batch_ids,
                            persist_directory=self.persist_dir,
                            collection_name="sejong_brain_jina_v5",
                        )
                    else:
                        time.sleep(2)  # 배치 간 2초 대기 (레이트 리밋 방지)
                        self.vectorstore.add_documents(documents=batch_chunks, ids=batch_ids)
                    
                    print(f"   ✅ 추가 완료: 배치 {batch_num}/{total_batches} ({len(batch_chunks)}개)")
                    break
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "Quota" in str(e):
                        wait = 15 * (attempt + 1)
                        print(f"   ⏳ 레이트 리밋 → {wait}초 대기 후 재시도 ({attempt + 1}/3)")
                        time.sleep(wait)
                    else:
                        raise

        self.all_chunks = chunks
        self._build_chain()
        print(f"✅ 인덱싱 완료! (저장: {self.persist_dir})")

    def load_index(self):
        """기존 벡터 DB 인덱스를 로드합니다."""
        if not os.path.exists(self.persist_dir):
            raise FileNotFoundError(
                f"벡터 DB가 없습니다: {self.persist_dir}\n"
                "먼저 python ingest.py 실행 후 index_documents()를 호출하세요."
            )

        self.vectorstore = Chroma(
            persist_directory=self.persist_dir,
            embedding_function=self.embeddings,
            collection_name="sejong_brain_jina_v5",
        )
        
        # BM25용 문서 로드
        all_docs = self.vectorstore.get()
        if all_docs and all_docs.get("documents"):
            self.all_chunks = [
                Document(
                    page_content=doc,
                    metadata=meta
                )
                for doc, meta in zip(all_docs["documents"], all_docs["metadatas"])
            ]
        
        self._build_chain()
        print(f"✅ 기존 인덱스 로드 완료 ({len(self.all_chunks)} 청크)")

    def _build_chain(self):
        """하이브리드 검색 RAG 체인을 구성합니다 (커스텀 RRF 결합)."""
        
        # BM25 키워드 검색 준비
        if self.all_chunks:
            self.bm25_retriever = BM25Retriever.from_documents(self.all_chunks)
            self.bm25_retriever.k = 5

        # 하이브리드 검색 함수 (Reciprocal Rank Fusion)
        def hybrid_search(question: str) -> List[Document]:
            """벡터 유사도 + BM25 키워드 검색을 RRF로 결합합니다."""
            # 1) 벡터 검색
            vector_results = []
            try:
                if self.vectorstore:
                    vector_results = self.vectorstore.similarity_search(question, k=5)
            except Exception as e:
                print(f"   ⚠️ 벡터 임베딩 한도 초과 오류 방지: {e} (BM25 전용 검색으로 우회합니다)")

            # 2) BM25 검색 (있으면)
            bm25_results = []
            if self.bm25_retriever:
                bm25_results = self.bm25_retriever.invoke(question)

            # 3) Reciprocal Rank Fusion
            doc_scores = {}   # page_content -> score
            doc_map = {}      # page_content -> Document

            k_param = 60  # RRF 파라미터
            
            for rank, doc in enumerate(vector_results):
                key = doc.page_content
                doc_scores[key] = doc_scores.get(key, 0) + (0.6 / (rank + k_param))
                doc_map[key] = doc

            for rank, doc in enumerate(bm25_results):
                key = doc.page_content
                # 벡터 없이 BM25만 될 경우 점수를 보정할 수도 있으나, 어차피 정렬용이므로 단순 합산 유지
                doc_scores[key] = doc_scores.get(key, 0) + (0.4 / (rank + k_param))
                doc_map[key] = doc

            # 점수 순 정렬, 상위 5개 반환
            sorted_keys = sorted(doc_scores.keys(), key=lambda k: doc_scores[k], reverse=True)
            return [doc_map[k] for k in sorted_keys[:5]]

        # RunnableLambda로 래핑
        retriever = RunnableLambda(hybrid_search)

        # 프롬프트 + LLM 체인
        prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)

        self.rag_chain = (
            {"context": retriever | self._format_docs, "question": RunnablePassthrough()}
            | prompt
            | self.llm
            | StrOutputParser()
        )

    def ask(self, question: str) -> Dict[str, Any]:
        """
        질문에 대한 RAG 기반 답변을 반환합니다.
        
        Returns:
            {
                "answer": "답변 텍스트",
                "sources": [{"title": "...", "page": 1}, ...],
                "question": "원본 질문"
            }
        """
        if not self.rag_chain:
            raise RuntimeError("RAG 체인이 초기화되지 않았습니다. index_documents() 또는 load_index()를 먼저 호출하세요.")

        # RAG 체인 실행
        answer = self.rag_chain.invoke(question)

        # 소스 문서 검색 (답변과 별도로)
        sources = self._get_sources(question)

        return {
            "answer": answer,
            "sources": sources,
            "question": question,
        }

    def _get_sources(self, question: str, k: int = TOP_K) -> List[Dict[str, Any]]:
        """질문과 관련된 소스 문서 정보를 반환합니다."""
        if not self.vectorstore and not self.bm25_retriever:
            return []

        docs = []
        try:
            if self.vectorstore:
                docs = self.vectorstore.similarity_search(question, k=k)
        except Exception as e:
            print(f"   ⚠️ 소스 검색 벡터 오류 (할당량 초과 등): {e}. BM25로 대체합니다.")
            if self.bm25_retriever:
                docs = self.bm25_retriever.invoke(question)[:k]
        
        sources = []
        seen = set()

        for doc in docs:
            meta = doc.metadata
            key = f"{meta.get('document_title', '')}-p{meta.get('page_number', '')}"
            if key not in seen:
                seen.add(key)
                
                page_val = meta.get("page_number")
                try:
                    page_val = int(page_val)
                except (ValueError, TypeError):
                    page_val = None
                    
                sources.append({
                    "title": meta.get("document_title", "알 수 없는 문서"),
                    "page": page_val,
                    "category": meta.get("category", ""),
                    "date": meta.get("publish_date", ""),
                    "source": meta.get("source", ""),
                })

        return sources

    @staticmethod
    def _format_docs(docs: List[Document]) -> str:
        """검색된 문서를 프롬프트용 문자열로 포맷합니다."""
        formatted = []
        for doc in docs:
            meta = doc.metadata
            header = f"[출처: {meta.get('document_title', '문서')}"
            try:
                page_num = int(meta.get('page_number'))
                header += f" p.{page_num}"
            except (ValueError, TypeError):
                pass
            header += "]"
            formatted.append(f"{header}\n{doc.page_content}")
        return "\n\n---\n\n".join(formatted)


def create_engine_from_scratch() -> RAGEngine:
    """데이터 인제스트 → 인덱싱 → 엔진 생성을 한번에 수행합니다."""
    sys.path.insert(0, PROJECT_ROOT)
    from ingest import ingest_all

    engine = RAGEngine()
    chunks = ingest_all()
    engine.index_documents(chunks)
    return engine


if __name__ == "__main__":
    print("🧠 SejongBrain RAG 엔진 테스트")
    print("=" * 50)

    # 엔진 생성 (인덱스가 없으면 새로 빌드)
    engine = RAGEngine()
    
    try:
        engine.load_index()
    except FileNotFoundError:
        print("📦 기존 인덱스가 없습니다. 새로 생성합니다...")
        engine = create_engine_from_scratch()

    # 테스트 질문
    test_questions = [
        "수강신청은 최대 몇 학점까지 할 수 있나요?",
        "장학금을 받으려면 한 학기에 몇 학점을 들어야 하나요?",
        "4학년은 장학금 기본이수학점이 다른가요?",
    ]

    for q in test_questions:
        print(f"\n{'─'*50}")
        print(f"❓ 질문: {q}")
        result = engine.ask(q)
        print(f"\n💬 답변:\n{result['answer']}")
        if result['sources']:
            print(f"\n📎 출처:")
            for s in result['sources']:
                print(f"   • {s['title']} (p.{s['page']})")
