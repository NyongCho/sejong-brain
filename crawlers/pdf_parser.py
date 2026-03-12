"""
PDF 파서 — 세종대학교 학사 문서 PDF를 텍스트로 변환합니다.
pdfplumber를 사용하여 테이블과 텍스트를 정확하게 추출합니다.
"""

import os
import pdfplumber
from typing import List, Dict, Any
from datetime import datetime


def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    PDF 파일을 페이지별 텍스트 + 메타데이터로 변환합니다.
    
    Returns:
        List of dicts: [
            {
                "text": "페이지 내용...",
                "metadata": {
                    "source": "파일경로",
                    "document_title": "2026-1학기 수강편람",
                    "page_number": 1,
                    "total_pages": 50,
                    "category": "수강편람",
                    "publish_date": "2026-02-13"
                }
            },
            ...
        ]
    """
    pages = []
    file_name = os.path.basename(file_path)
    doc_title = _extract_title(file_name)
    publish_date = _extract_date(file_name)
    category = _classify_category(file_name)

    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()

            # 테이블이 있으면 텍스트 형태로 추가 추출
            tables = page.extract_tables()
            table_text = _tables_to_text(tables)

            combined_text = ""
            if text:
                combined_text += text.strip()
            if table_text:
                combined_text += "\n\n" + table_text

            if combined_text.strip():
                pages.append({
                    "text": combined_text.strip(),
                    "metadata": {
                        "source": file_path,
                        "document_title": doc_title,
                        "page_number": page_num,
                        "total_pages": total_pages,
                        "category": category,
                        "publish_date": publish_date,
                    }
                })

    return pages


def _tables_to_text(tables: list) -> str:
    """테이블 데이터를 Markdown 형식의 텍스트로 변환합니다."""
    if not tables:
        return ""
    
    parts = []
    for table in tables:
        if not table or not table[0]:
            continue
            
        # 첫 번째 행을 헤더로 처리
        headers = [str(cell).strip().replace('\n', ' ') if cell else "" for cell in table[0]]
        parts.append("| " + " | ".join(headers) + " |")
        parts.append("|" + "|".join(["---"] * len(headers)) + "|")
        
        # 나머지 행
        for row in table[1:]:
            if not row:
                continue
            cells = [str(cell).strip().replace('\n', ' ') if cell else "" for cell in row]
            # 행 길이가 헤더 길이와 다를 경우 맞춤
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            elif len(cells) > len(headers):
                cells = cells[:len(headers)]
                
            parts.append("| " + " | ".join(cells) + " |")
        parts.append("\n")
    
    return "\n".join(parts)


def _extract_title(filename: str) -> str:
    """파일명에서 문서 제목을 추출합니다."""
    name = os.path.splitext(filename)[0]
    # 날짜 패턴 제거 (예: _20260213)
    import re
    name = re.sub(r'_\d{8}$', '', name)
    return name.strip()


def _extract_date(filename: str) -> str:
    """파일명에서 날짜를 추출합니다 (YYYYMMDD → YYYY-MM-DD)."""
    import re
    match = re.search(r'(\d{8})', filename)
    if match:
        date_str = match.group(1)
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def _classify_category(filename: str) -> str:
    """파일명 키워드 기반으로 문서 카테고리를 분류합니다."""
    keyword_map = {
        "수강편람": "수강",
        "수강": "수강",
        "장학": "장학",
        "졸업": "졸업",
        "학칙": "학칙",
        "내규": "학칙",
        "교육과정": "교육과정",
        "등록": "등록",
        "공지": "공지",
    }
    for keyword, category in keyword_map.items():
        if keyword in filename:
            return category
    return "기타"


def parse_all_pdfs(directory: str) -> List[Dict[str, Any]]:
    """디렉토리 내 모든 PDF를 파싱합니다."""
    all_pages = []
    for filename in os.listdir(directory):
        if filename.lower().endswith('.pdf'):
            file_path = os.path.join(directory, filename)
            print(f"📄 PDF 파싱 중: {filename}")
            pages = parse_pdf(file_path)
            all_pages.extend(pages)
            print(f"   → {len(pages)} 페이지 추출 완료")
    return all_pages


if __name__ == "__main__":
    # 테스트: 기존 수강편람 PDF 파싱
    import sys
    
    pdf_path = os.path.join(os.path.dirname(__file__), "..", "2026-1학기 수강편람_20260213.pdf")
    
    if not os.path.exists(pdf_path):
        print(f"❌ 파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)
    
    pages = parse_pdf(pdf_path)
    print(f"\n✅ 총 {len(pages)} 페이지 파싱 완료\n")
    
    # 첫 3페이지 미리보기
    for page in pages[:3]:
        meta = page["metadata"]
        print(f"--- 📖 {meta['document_title']} (p.{meta['page_number']}) ---")
        print(page["text"][:300])
        print()
