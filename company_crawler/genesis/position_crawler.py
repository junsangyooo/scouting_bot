from playwright.sync_api import sync_playwright, TimeoutError
from typing import List, Dict
import hashlib
import time

# Genesis AI hosts its jobs on Ashby (same platform as DYNA / Sunday). The
# careers page links directly to each Ashby detail page and already carries
# title / department / location / workplace inline, so we crawl the careers
# page for the job list, then visit each Ashby detail page for the full JD.
CAREERS_URL = "https://www.genesis.ai/careers"
ASHBY_HOST = "https://jobs.ashbyhq.com"
ASHBY_MARKER = "jobs.ashbyhq.com/genesis-ai/"


def position_crawler() -> List[Dict]:
    positions: List[Dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(CAREERS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        # 1️⃣ 채용 공고 목록 수집 (careers 페이지의 Ashby 링크)
        jobs = page.eval_on_selector_all(
            'a[href*="jobs.ashbyhq.com/genesis-ai/"]',
            """els => {
                const seen = new Set();
                const out = [];
                els.forEach(a => {
                    const href = a.getAttribute('href') || '';
                    if (!href || seen.has(href)) return;
                    seen.add(href);
                    const lines = (a.innerText || '')
                        .split('\\n')
                        .map(l => l.trim())
                        .filter(Boolean)
                        .filter(l => l.toLowerCase() !== 'apply');
                    out.push({ href, lines });
                });
                return out;
            }""",
        )

        print(f"[INFO] Found {len(jobs)} position links")

        # 2️⃣ 각 공고의 Ashby 상세 페이지에서 JD/보상 추출
        for idx, job in enumerate(jobs):
            href = job["href"]
            lines = job["lines"]
            if not lines:
                continue

            # careers 카드 라인: [title, department, location, workplace]
            title = lines[0]
            department = lines[1] if len(lines) > 1 else ""
            location = lines[2] if len(lines) > 2 else ""
            workplace = lines[3] if len(lines) > 3 else ""

            # Ashby UUID를 안정적인 id로 사용 (제목 중복 location 문제 회피)
            job_id = href.rstrip("/").split("/")[-1]

            print(f"[INFO] ({idx+1}/{len(jobs)}) Processing: {title}")

            detail = _extract_detail(page, href)
            description = detail["description"]
            location = detail["location"] or location
            compensation = detail["compensation"]

            if not description:
                print(f"[WARN] Empty description: {title}")

            positions.append({
                "id": job_id,
                "title": title,
                "department": department,
                "location": location,
                "workplace": workplace,
                "compensation": compensation,
                "description": description,
                "description_hash": _hash_text(description),
                "url": href,
            })

            time.sleep(0.5)  # polite delay

        browser.close()

    return positions


def _extract_detail(page, url, retries=3) -> Dict:
    """Ashby 상세 페이지에서 location / compensation / description 추출."""
    full_url = url if url.startswith("http") else f"{ASHBY_HOST}{url}"

    for attempt in range(retries):
        try:
            page.goto(full_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(1500)

            data = page.evaluate("""
                () => {
                    const result = { location: '', compensation: '', description: '' };

                    // Left pane: Location / Compensation
                    const sections = document.querySelectorAll('div[class*="section"]');
                    sections.forEach(section => {
                        const heading = section.querySelector('h2');
                        if (!heading) return;
                        const headingText = heading.innerText.trim().toLowerCase();
                        if (headingText === 'location') {
                            const content = section.querySelector('p');
                            if (content) result.location = content.innerText.trim();
                        } else if (headingText === 'compensation') {
                            const compSpan = section.querySelector('span[class*="compensationTierSummary"]');
                            if (compSpan) {
                                result.compensation = compSpan.innerText.trim();
                            } else {
                                const content = section.querySelector('p');
                                if (content) result.compensation = content.innerText.trim();
                            }
                        }
                    });

                    // Description (HTML -> 읽기 좋은 텍스트)
                    const descEl = document.querySelector('div[class*="descriptionText"], .ashby-job-posting-description');
                    if (descEl) {
                        const clone = descEl.cloneNode(true);
                        clone.querySelectorAll('h2').forEach(h2 => {
                            h2.innerHTML = '\\n\\n## ' + h2.innerText + '\\n';
                        });
                        clone.querySelectorAll('li').forEach(li => {
                            li.innerHTML = '• ' + li.innerText + '\\n';
                        });
                        clone.querySelectorAll('p').forEach(p => {
                            if (p.innerText.trim()) p.innerHTML = p.innerText + '\\n';
                        });
                        result.description = clone.innerText.trim();
                    }

                    return result;
                }
            """)

            if data["description"] and len(data["description"]) >= 30:
                return data
            # description이 비어도 location은 잡혔을 수 있으니 마지막 시도면 반환
            if attempt == retries - 1:
                return data

        except TimeoutError:
            print(f"[WARN] Attempt {attempt+1}/{retries} timeout for {full_url}")
        except Exception as e:
            print(f"[WARN] Attempt {attempt+1}/{retries} error: {e}")

    return {"location": "", "compensation": "", "description": ""}


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


if __name__ == "__main__":
    data = position_crawler()
    print(f"\n[RESULT] Crawled {len(data)} positions\n")
    for pos in data:
        print(f"  - {pos['title']} | {pos['location']} | {pos['workplace']}")
        print(f"    comp: {pos['compensation']!r}  desc: {len(pos['description'])} chars")
