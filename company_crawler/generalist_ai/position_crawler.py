from playwright.sync_api import sync_playwright, TimeoutError
from urllib.parse import quote
import hashlib
import time

CAREERS_URL = "https://generalistai.com/careers"

# 상세 설명에서 제거할 공통 텍스트
_BOILERPLATE_MARKERS = [
    "About Generalist",
    "We are an equal opportunity employer",
    "Apply for this position",
]


def position_crawler():
    positions = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(CAREERS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # 1️⃣ 채용 공고 목록 수집
        jobs = page.eval_on_selector_all(
            'a[href*="/careers?posting="]',
            """els => els.map(a => {
                const title = a.querySelector('.careers-listing-title');
                const meta = a.querySelector('.careers-listing-meta');
                const metaText = meta ? meta.innerText.trim() : '';
                const parts = metaText.split('\\n').map(l => l.trim()).filter(Boolean);
                return {
                    href: a.getAttribute('href') || '',
                    title: title ? title.innerText.trim() : '',
                    department: parts[0] || '',
                    location: parts[1] || '',
                    posting_id: (a.getAttribute('href') || '').split('posting=')[1] || '',
                };
            })""",
        )

        print(f"[INFO] Found {len(jobs)} position links")

        # 2️⃣ 각 공고 상세 페이지에서 JD 추출
        for idx, job in enumerate(jobs):
            title = job["title"]
            posting_id = job["posting_id"]
            location = job["location"]
            print(f"[INFO] ({idx+1}/{len(jobs)}) Processing: {title}")

            description = _extract_description(page, posting_id)
            if not description:
                print(f"[WARN] Empty description: {title}")
                continue

            positions.append({
                # Use the unique Ashby posting UUID as id, not a title slug —
                # two postings can share a title (e.g. "Office Manager" SFO + BOS),
                # and a slug collision silently merges them (one role becomes
                # invisible to open/close tracking and headcount/velocity disagree).
                "id": posting_id or _make_job_id(title),
                "title": title,
                "location": location,
                "compensation": "",
                "description": description,
                "description_hash": _hash_text(description),
                "url": f"{CAREERS_URL}?posting={posting_id}",
            })

            time.sleep(0.5)

        browser.close()

    return positions


def _extract_description(page, posting_id, retries=3):
    url = f"{CAREERS_URL}?posting={posting_id}"

    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            detail = page.query_selector(".careers-detail")
            if not detail:
                continue

            raw_text = detail.inner_text().strip()
            if not raw_text or len(raw_text) < 50:
                continue

            return _clean_description(raw_text)

        except TimeoutError:
            print(f"[WARN] Attempt {attempt+1}/{retries} timeout for {posting_id}")
        except Exception as e:
            print(f"[WARN] Attempt {attempt+1}/{retries} error: {e}")

    return ""


def _clean_description(text):
    lines = text.split("\n")
    lines = [l.strip() for l in lines]

    # "← All positions" 제거
    if lines and lines[0].startswith("←"):
        lines = lines[1:]

    # 하단 보일러플레이트 제거 ("About Generalist" 이후)
    cleaned = []
    for line in lines:
        if any(line.startswith(marker) for marker in _BOILERPLATE_MARKERS):
            break
        cleaned.append(line)

    # 빈 줄 정리
    result = []
    for line in cleaned:
        if line:
            result.append(line)

    return "\n\n".join(result)


def _make_job_id(title):
    return quote(title.lower().replace(" ", "-"))


def _hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
