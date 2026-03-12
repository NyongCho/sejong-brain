import requests
from bs4 import BeautifulSoup
import re

url = "https://www.sejong.ac.kr/kor/intro/notice3.do?mode=view&articleNo=863954"
# url = "https://www.sejong.ac.kr/kor/intro/notice3.do?mode=view&articleNo=80532"

# 봇(Bot) 차단을 방지하기 위해 일반 브라우저로 위장하는 User-Agent를 넣어줍니다.
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

try:
    response = requests.get(url, headers=headers)
    print(response.status_code)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        # 날짜 정보 찾기 (년도 추출)
        date_text = soup.find('li', class_='b-date')
        print(date_text.text.strip())
        if date_text:
            year = re.search(r'(\d{4})', date_text.text)
            if year:
                print(f"작성 년도: {year.group(1)}")

        main_info = soup.find('div', class_='b-title-box')
        print('=== Main Info ===')
        print(main_info.text)

        main_contents = soup.select_one('div.b-content-box')
        print('=== Main Contents ===')
        print(main_contents.get_text(strip=True, separator="<END>\n"))
    
except requests.exceptions.RequestException as e:
    print(f"요청 실패: {e}")
