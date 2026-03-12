"""
세종대학교 학사공지 웹 크롤러
지정된 articleNo 범위를 순회하며 학사공지 게시글을 수집하고, JSON 파일로 로컬에 저장합니다.
"""

import os
import time
import json
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any

# 다운로드 디렉토리 설정
SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "crawled", "academic_notices")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0'
}

def crawl_academic_notice(article_no: int) -> Dict[str, Any]:
    """특정 articleNo의 학사공지를 크롤링합니다."""
    url = f"https://www.sejong.ac.kr/kor/intro/notice3.do?mode=view&articleNo={article_no}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 글이 삭제되었거나 존재하지 않는 경우의 패턴 확인 (예: alert 발생 등)
        if "게시물이 존재하지 않습니다" in response.text or "권한이 없습니다" in response.text:
            return None
            
        # 제목 파싱
        title_elem = soup.find('div', class_='b-title-box')
        if not title_elem:
            # 문서 구조가 맞지 않거나 글이 없음
            return None
            
        title = title_elem.text.strip()
        
        # 내용 파싱
        content_elem = soup.select_one('div.b-content-box')
        if not content_elem:
            content = ""
        else:
            content = content_elem.get_text(strip=True, separator="\n")
            
        # 작성일 파싱
        date = ""
        date_elem = soup.find('li', class_='b-date')
        if date_elem:
            date = date_elem.text.strip()
        
        # 만약 본문 내용이 거의 없다면 무의미한 게시물로 취급
        if len(title) == 0 and len(content) == 0:
            return None
            
        return {
            "id": article_no,
            "url": url,
            "title": title,
            "date": date,
            "category": "학사공지",
            "content": content
        }
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️ 요청 오류 (articleNo={article_no}): {e}")
        return None
    except Exception as e:
        print(f"⚠️ 파싱 오류 (articleNo={article_no}): {e}")
        return None

def main(start_id: int = 805992, end_id: int = 864156):
    print("🎓 세종대 학사공지 크롤러를 시작합니다.")
    print(f"👉 대상 범위: {start_id} ~ {end_id} (총 {end_id - start_id + 1}건)")
    
    os.makedirs(SAVE_DIR, exist_ok=True)
    
    success_count = 0
    missing_count = 0
    session = requests.Session()
    session.headers.update(HEADERS)
    
    for article_no in range(start_id, end_id + 1):
        # 이미 수집한 파일이 있으면 건너뛰기
        filepath = os.path.join(SAVE_DIR, f"{article_no}.json")
        if os.path.exists(filepath):
            print('Already exist')  
            success_count += 1
            continue
            
        # 너무 잦은 요청 시 진행 상황 표시 (예: 100건 단위)
        if (article_no - start_id) % 100 == 0:
            print(f"🔍 진행 중: {article_no} / {end_id} (성공: {success_count}, 없음: {missing_count})")
            
        data = crawl_academic_notice(article_no)
        print(data)
        if data:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            success_count += 1
            print(f"  ✅ 수집 완료: [{article_no}] {data['title']}")
        else:
            missing_count += 1
            
        time.sleep(0.5) # 서버 부하 방지용 (필요시 조절)
        
    print(f"🎉 크롤링 완료! (성공: {success_count}, 없음/오류: {missing_count})")
    print(f"📂 저장 경로: {SAVE_DIR}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='세종대학교 학사공지 크롤러')
    parser.add_argument('--start', type=int, default=863800, help='시작 articleNo (기본: 최근공지 근처 863800)') # 테스트를 위해 작은 범위로 기본값 설정
    parser.add_argument('--end', type=int, default=864156, help='종료 articleNo')
    args = parser.parse_args()
    
    # main(args.start, args.end)
    main()
