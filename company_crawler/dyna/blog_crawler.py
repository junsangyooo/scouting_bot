from playwright.sync_api import sync_playwright
import hashlib
import re
import time

BASE_URL = "https://www.dyna.co"
DYNA_RESEARCH_URL = f"{BASE_URL}/research"

def generate_id(title: str, date: str) -> str:
    return hashlib.md5(f"{title}_{date}".encode()).hexdigest()

def parse_date(raw: str) -> str:
    """
    'JUN 15 '25' -> '2025-06-15'
    """
    match = re.match(r"([A-Z]{3})\s+(\d{1,2})\s+'(\d{2})", raw.strip())
    if not match:
        return raw
    month_str, day, year_short = match.groups()
    months = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
        "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
        "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
    }
    month = months.get(month_str, "01")
    year = f"20{year_short}"
    return f"{year}-{month}-{day.zfill(2)}"

def blog_crawler():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(DYNA_RESEARCH_URL, wait_until="networkidle")
        time.sleep(2)  # 페이지 완전 로딩 대기

        # 페이지 전체 HTML에서 카드 정보와 URL 추출
        # JavaScript로 직접 데이터 수집
        card_data = page.evaluate("""
            () => {
                const cards = document.querySelectorAll('div.flex.flex-col.mb-16');
                const results = [];

                cards.forEach((card, index) => {
                    const title = card.querySelector('h2')?.innerText?.trim() || '';
                    const excerpt = card.querySelector('p.leading-relaxed')?.innerText?.trim() || '';

                    // 날짜 찾기
                    let date = '';
                    const divs = card.querySelectorAll('div.mb-4');
                    divs.forEach(div => {
                        const text = div.innerText?.trim() || '';
                        if (/[A-Z]{3}\\s+\\d{1,2}\\s+'?\\d{2}/.test(text)) {
                            date = text;
                        }
                    });

                    results.push({
                        title: title,
                        excerpt: excerpt,
                        date_raw: date,
                        index: index
                    });
                });

                return results;
            }
        """)

        print(f"[INFO] Found {len(card_data)} research cards")

        # 각 카드의 Read More 버튼 클릭하여 URL 수집
        for data in card_data:
            print(f"[INFO] Processing: {data['title']}")

            final_url = None

            try:
                # JavaScript로 버튼 클릭
                before_url = page.url

                clicked = page.evaluate(f"""
                    () => {{
                        const cards = document.querySelectorAll('div.flex.flex-col.mb-16');
                        const card = cards[{data['index']}];
                        if (!card) return false;

                        const btn = card.querySelector('button');
                        if (btn) {{
                            btn.click();
                            return true;
                        }}
                        return false;
                    }}
                """)

                if not clicked:
                    print(f"[WARN] Could not click button for: {data['title']}")
                else:
                    # URL 변경 대기
                    max_wait = 10
                    waited = 0
                    while waited < max_wait:
                        time.sleep(0.5)
                        waited += 0.5
                        current_url = page.url
                        if current_url != before_url:
                            final_url = current_url
                            print(f"[INFO] URL found: {final_url}")
                            break

                    # 리서치 페이지로 돌아가기
                    if final_url:
                        page.goto(DYNA_RESEARCH_URL, wait_until="networkidle")
                        time.sleep(1)

            except Exception as e:
                print(f"[ERROR] {data['title']}: {e}")
                try:
                    page.goto(DYNA_RESEARCH_URL, wait_until="networkidle")
                    time.sleep(1)
                except:
                    pass

            date_formatted = parse_date(data["date_raw"])
            item_id = generate_id(data["title"], date_formatted)

            results.append({
                "id": item_id,
                "title": data["title"],
                "date": date_formatted,
                "type": "research",
                "excerpt": data["excerpt"],
                "url": final_url
            })

        browser.close()
    return results

if __name__ == "__main__":
    data = blog_crawler()
    print(f"\n[RESULT] Total {len(data)} items crawled:\n")
    for item in data:
        print(f"  - {item['title']}")
        print(f"    Date: {item['date']}")
        print(f"    URL: {item['url']}")
        print()
