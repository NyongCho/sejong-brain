"""
데이터 인제스트 파이프라인 (통합/모듈화)
PDF 문서, 크롤링된 JSON 웹 공지사항 등 다양한 소스의 데이터를 읽어와
청킹 후 ChromaDB에 임베딩하여 저장합니다.
"""

import os
import sys
import json
import glob
import argparse
from typing import List, Optional
from langchain_core.documents import Document

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawlers.pdf_parser import parse_pdf
from processors.chunker import create_chunks, create_safe_semantic_chunks_from_text

# 경로 설정
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_RAW = os.path.join(PROJECT_ROOT, "data", "raw")
DATA_CRAWLED = os.path.join(PROJECT_ROOT, "data", "crawled", "academic_notices")
DATA_PROCESSED = os.path.join(PROJECT_ROOT, "data", "processed")

def ingest_pdfs(pdf_dir: Optional[str] = None, chunk_size: int = 4000, chunk_overlap: int = 500) -> List[Document]:
    """PDF 파일들을 찾아 청크로 변환합니다."""
    chunks = []
    search_dirs = [pdf_dir] if pdf_dir else [PROJECT_ROOT, DATA_RAW]
    
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
            
        pdf_files = glob.glob(os.path.join(search_dir, "*.pdf"))
        for pdf_path in pdf_files:
            print(f"\n📄 PDF 처리 중: {os.path.basename(pdf_path)}")
            pages = parse_pdf(pdf_path)
            doc_chunks = create_chunks(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            chunks.extend(doc_chunks)
            print(f"   → {len(pages)} 페이지 → {len(doc_chunks)} 청크")
            
    return chunks

def ingest_crawled_data(crawled_dir: str = DATA_CRAWLED, max_chunk_size: int = 4000, chunk_overlap: int = 500) -> List[Document]:
    """크롤링하여 저장된 JSON 파일들을 시맨틱 청킹으로 변환합니다."""
    chunks = []
    if not os.path.exists(crawled_dir):
        print(f"\n⚠️ 크롤링된 데이터 폴더가 없습니다: {crawled_dir}")
        return chunks
        
    json_files = glob.glob(os.path.join(crawled_dir, "*.json"))
    if not json_files:
        print(f"\n⚠️ 크롤링된 JSON 데이터가 없습니다.")
        return chunks
    
    # 시맨틱 청커용 임베딩 모델을 1회만 로드하여 공유 (매 파일마다 로드 방지)
    from langchain_huggingface import HuggingFaceEmbeddings
    print(f"\n🔄 시맨틱 청커용 임베딩 모델 로드 중...")
    shared_embeddings = HuggingFaceEmbeddings(
        model_name="jinaai/jina-embeddings-v5-text-small",
        model_kwargs={'trust_remote_code': True},
        encode_kwargs={'task': 'retrieval'}
    )
        
    print(f"\n🌐 크롤링 데이터 처리 중: 총 {len(json_files)}개 파일 (시맨틱 청킹 적용)")
    for json_path in json_files:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            metadata = {
                "source": data.get("url", json_path),
                "document_title": data.get("title", "제목 없음"),
                "category": data.get("category", "학사공지"),
                "publish_date": data.get("date", ""),
            }
            
            content = data.get("content", "")
            if not content:
                continue
                
            doc_chunks = create_safe_semantic_chunks_from_text(
                content, metadata,
                embeddings=shared_embeddings,
                max_chunk_size=max_chunk_size,
                chunk_overlap=chunk_overlap,
            )
            chunks.extend(doc_chunks)
        except Exception as e:
            print(f"   ⚠️ 파일 읽기 오류 ({json_path}): {e}")
            
    print(f"   → 총 {len(chunks)} 청크 생성")
    return chunks

def save_chunks_json(chunks: List[Document], output_path: Optional[str] = None):
    """청크 데이터를 JSON으로 백업 저장합니다 (디버깅/조회용)."""
    if not chunks:
        return
        
    if output_path is None:
        os.makedirs(DATA_PROCESSED, exist_ok=True)
        output_path = os.path.join(DATA_PROCESSED, "chunks.json")
    
    data = []
    for chunk in chunks:
        data.append({
            "text": chunk.page_content,
            "metadata": chunk.metadata,
        })
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 청크 데이터 백업 저장 완료: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="SejongBrain 데이터 인제스트 파이프라인")
    parser.add_argument("--pdf", action="store_true", help="PDF 파일만 처리합니다.")
    parser.add_argument("--crawled", action="store_true", help="크롤링된 JSON 파일 목록만 처리합니다.")
    parser.add_argument("--all", action="store_true", help="모든 소스(PDF, Crawled JSON)를 처리합니다.")
    parser.add_argument("--no-embed", action="store_true", help="벡터 임베딩 구동 과정을 건너뛰고 청크만 생성(JSON 저장)합니다.")
    parser.add_argument("--force", action="store_true", help="기존 ChromaDB를 초기화하고 처음부터 다시 인덱싱합니다.")
    args = parser.parse_args()

    # 기본값은 모두 처리
    if not args.pdf and not args.crawled and not args.all:
        args.all = True

    print("🎓 SejongBrain 데이터 인제스트 파이프라인")
    print("=" * 50)

    all_chunks = []
    
    if args.all or args.pdf:
        all_chunks.extend(ingest_pdfs())
        
    if args.all or args.crawled:
        all_chunks.extend(ingest_crawled_data())

    if not all_chunks:
        print("\n⚠️ 처리할 데이터/청크가 없습니다.")
        return

    print(f"\n{'='*50}")
    print(f"✅ 총 {len(all_chunks)}개 청크 생성 완료")
    print(f"{'='*50}")

    # 백업용 파일 저장
    save_chunks_json(all_chunks)

    # 카테고리 통계 출력
    categories = {}
    for chunk in all_chunks:
        cat = chunk.metadata.get("category", "기타")
        categories[cat] = categories.get(cat, 0) + 1
    
    print(f"\n📊 카테고리별 청크 수:")
    for cat, count in sorted(categories.items()):
        print(f"   {cat}: {count}개")

    if args.no_embed:
        print("\n🚫 '--no-embed' 플래그가 적용되어 ChromaDB 임베딩을 건너뜁니다.")
        return

    # --force: 기존 ChromaDB 삭제 후 새로 인덱싱
    if args.force:
        import shutil
        chroma_dir = os.path.join(PROJECT_ROOT, "data", "chromadb")
        if os.path.exists(chroma_dir):
            shutil.rmtree(chroma_dir)
            print("\n🗑️  기존 ChromaDB를 삭제했습니다. 새로 인덱싱합니다...")

    print("\n🧠 벡터 DB(ChromaDB) 갱신을 시작합니다...")
    from backend.rag_engine import RAGEngine
    engine = RAGEngine()
    
    # 중복 방지 로직이 포함된 index_documents 호출
    engine.index_documents(all_chunks)

if __name__ == "__main__":
    main()
