from playwright.sync_api import sync_playwright, TimeoutError
from urllib.parse import quote
import time

JOIN_US_URL = "https://www.pi.website/join-us"


def position_crawler():
    positions = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(JOIN_US_URL, timeout=30000)
        page.wait_for_load_state("networkidle")

        buttons = page.locator("ul li button")
        total = buttons.count()
        print(f"[INFO] Found {total} position buttons")

        for i in range(total):
            btn = buttons.nth(i)
            title = btn.inner_text().strip()

            if not title:
                continue

            print(f"[INFO] Processing: {title}")

            try:
                # 1️⃣ 버튼 클릭
                btn.scroll_into_view_if_needed()
                btn.click(force=True)

                # 2️⃣ iframe 생성 대기 (더 길게)
                page.wait_for_selector("iframe", state="attached", timeout=20000)

                # 추가 대기: iframe이 DOM에 완전히 로드되도록
                time.sleep(1.5)

                # 3️⃣ iframe에 직접 접근
                iframe_element = page.query_selector("iframe")
                if not iframe_element:
                    print(f"[WARN] No iframe found: {title}")
                    continue

                frame = iframe_element.content_frame()
                if not frame:
                    print(f"[WARN] Cannot access iframe content: {title}")
                    continue

                # 4️⃣ iframe 내부 컨텐츠 로드 대기
                # 실제 JD 내용이 있는 요소가 나타날 때까지 대기
                try:
                    # Ashby iframe 내부에 실제 job description이 로드될 때까지 대기
                    frame.wait_for_selector("div[class*='job'], div[class*='description'], p, h1, h2",
                                          state="visible",
                                          timeout=10000)
                except TimeoutError:
                    print(f"[WARN] JD content not loaded in iframe: {title}")
                    continue

                # 추가 대기 (컨텐츠가 완전히 렌더링되도록)
                time.sleep(1)

                # 5️⃣ iframe 안의 "보이는 텍스트 전체" 추출
                raw_text = frame.locator("body").inner_text()

                if not raw_text or len(raw_text.strip()) < 100:
                    print(f"[WARN] Empty JD text: {title}")
                    print(f"[DEBUG] Text length: {len(raw_text.strip()) if raw_text else 0}")
                    continue

                description = _clean_ashby_text(raw_text)

                positions.append({
                    "id": _make_job_id(title),
                    "title": title,
                    "description": description
                })

                time.sleep(0.4)

            except TimeoutError:
                print(f"[WARN] Timeout while processing: {title}")
                continue

            except Exception as e:
                print(f"[ERROR] Failed position {title}: {e}")
                continue

        browser.close()

    return positions


# ---------- helpers ----------

def _make_job_id(title: str) -> str:
    """
    Stable ID based on title (Ashby URL은 안 쓰는 구조)
    """
    return quote(title.lower().replace(" ", "-"))


def _clean_ashby_text(text: str) -> str:
    """
    Ashby iframe innerText 후처리
    """
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]

    blacklist = {
        "Apply",
        "Back",
        "Apply for this job",
        "Physical Intelligence"
    }

    cleaned = []
    for line in lines:
        if line in blacklist:
            continue
        cleaned.append(line)

    return "\n\n".join(cleaned)
