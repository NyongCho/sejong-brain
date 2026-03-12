"""
시맨틱 청킹 엔진 — 한국어 문서를 의미 단위로 분할합니다.
고정 크기 분할이 아닌, 한국어 문장 종결 패턴을 존중하는 분할 전략을 사용합니다.
"""

from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document


# 한국어에 최적화된 분리자 우선순위
KOREAN_SEPARATORS = [
    "\n\n",                    # 단락 구분 (최우선)
    "\n",                      # 줄바꿈
    "다. ",                    # 한국어 문장 종결
    "한다. ",
    "있다. ",
    "된다. ",
    "않다. ",
    "이다. ",
    "니다. ",                  # 존댓말 종결 (습니다, 합니다)
    "세요. ",                  # 존댓말 종결 (하세요)
    ". ",                      # 일반 문장 종결
    " ",                       # 공백 (최후 수단)
]


def create_chunks(
    pages: List[Dict[str, Any]],
    chunk_size: int = 4000,
    chunk_overlap: int = 400
) -> List[Document]:
    """
    PDF 파서의 출력(페이지 리스트)을 LangChain Document 청크로 변환합니다.
    
    Args:
        pages: pdf_parser.parse_pdf()의 결과물
        chunk_size: 청크 최대 크기 (Jina Embeddings v5는 최대 32K 토큰을 지원하므로 크기를 키움)
        chunk_overlap: 청크 간 오버랩 (문맥 유지)
    
    Returns:
        List[Document]: 메타데이터가 포함된 LangChain Document 리스트
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=KOREAN_SEPARATORS,
        length_function=len,
        is_separator_regex=False,
    )

    all_chunks = []

    for page in pages:
        # 페이지 텍스트를 Document로 변환
        doc = Document(
            page_content=page["text"],
            metadata=page["metadata"]
        )

        # 시맨틱 분할
        page_chunks = text_splitter.split_documents([doc])

        # 각 청크에 청크 인덱스 메타데이터 추가
        for idx, chunk in enumerate(page_chunks):
            chunk.metadata["chunk_index"] = idx
            chunk.metadata["chunk_total"] = len(page_chunks)

        all_chunks.extend(page_chunks)

    return all_chunks


def create_safe_semantic_chunks_from_text(
    text: str,
    metadata: Dict[str, Any],
    embeddings = None, # 임베딩 모델을 외부에서 주입받도록 변경
    max_chunk_size: int = 4000,
    chunk_overlap: int = 500,
    breakpoint_type: str = "percentile",
    breakpoint_amount: float = 95.0
) -> List[Document]:
    """
    일반 텍스트를 '의미(문맥)' 기반으로 청크 분할합니다.
    
    Args:
        text: 원본 텍스트
        metadata: 첨부할 메타데이터 dict
        embeddings: 텍스트 유사도를 계산할 임베딩 모델 (필수)
        breakpoint_type: 절벽을 계산할 방식 (percentile, standard_deviation 등)
        breakpoint_amount: 절벽의 기준값 (기본 95.0 백분위수)
    
    Returns:
        List[Document]: 의미 단위로 분할된 청크 리스트
    """
    
    # 1. 임베딩 모델 세팅 (없으면 Local Jina)
    if embeddings is None:
        embeddings = HuggingFaceEmbeddings(
            model_name="jinaai/jina-embeddings-v5-text-small",
            model_kwargs={'trust_remote_code': True},
            encode_kwargs={'task': 'retrieval'}
        )

    # 2. 시맨틱 청커 초기화 (크기, 오버랩 대신 절벽 기준 세팅)
    text_splitter = SemanticChunker(
        embeddings=embeddings,
        breakpoint_threshold_type=breakpoint_type,
        breakpoint_threshold_amount=breakpoint_amount,
    )

    backup_chunker = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_size,
        chunk_overlap=chunk_overlap,
        separators=KOREAN_SEPARATORS,
        length_function=len,
        is_separator_regex=False,
    )

    # 3. 문서 객체 생성 및 분할 (기존 구조 동일)
    doc = Document(page_content=text, metadata=metadata)
    initial_chunks = text_splitter.split_documents([doc])

    final_chunks = []

    for chunk in initial_chunks:
        if len(chunk.page_content) > max_chunk_size:
            forced_chunks = backup_chunker.split_documents([chunk])
            final_chunks.extend(forced_chunks)
        else:
            final_chunks.append(chunk)

    # 4. 메타데이터 인덱싱 (작성하신 훌륭한 로직 그대로 유지!)
    for idx, chunk in enumerate(final_chunks):
        chunk.metadata["chunk_index"] = idx
        chunk.metadata["chunk_total"] = len(final_chunks)

    return final_chunks

def create_chunks_from_text(
    text: str,
    metadata: Dict[str, Any],
    chunk_size: int = 4000,
    chunk_overlap: int = 400
) -> List[Document]:
    """
    일반 텍스트(공지사항 등)를 청크로 분할합니다.
    
    Args:
        text: 원본 텍스트
        metadata: 첨부할 메타데이터 dict
        chunk_size: 청크 최대 크기
        chunk_overlap: 오버랩 크기
    
    Returns:
        List[Document]: 청크 리스트
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=KOREAN_SEPARATORS,
        length_function=len,
        is_separator_regex=False,
    )

    doc = Document(page_content=text, metadata=metadata)
    chunks = text_splitter.split_documents([doc])

    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = idx
        chunk.metadata["chunk_total"] = len(chunks)

    return chunks


if __name__ == "__main__":
    # 테스트: 기존 dummy_policy.txt 를 새 청킹 설정으로 분할
    import os
    
    test_file = os.path.join(os.path.dirname(__file__), "..", "dummy_policy.txt")
    
    with open(test_file, "r", encoding="utf-8") as f:
        text = f.read()
    
    metadata = {
        "source": test_file,
        "document_title": "수강신청 정책",
        "category": "수강",
        "publish_date": "2026-02-13",
    }
    
    chunks = create_safe_semantic_chunks_from_text(text, metadata, chunk_size=500, chunk_overlap=100)
    
    print(f"✅ 총 {len(chunks)}개 청크 생성 (chunk_size=500, overlap=100)\n")
    
    for i, chunk in enumerate(chunks):
        print(f"--- 청크 {i+1}/{len(chunks)} ({len(chunk.page_content)}자) ---")
        print(chunk.page_content[:200])
        print(f"  📌 메타: {chunk.metadata}")
        print()
