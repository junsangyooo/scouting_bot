from playwright.sync_api import sync_playwright, TimeoutError
from typing import List, Dict
import hashlib
import time

# Rhoda AI hosts its jobs on Ashby (same platform as DYNA / Sunday / Genesis).
# rhoda.ai/careers merely embeds the Ashby board in an iframe
# (<iframe src="https://jobs.ashbyhq.com/rhoda-ai?embed=js">), so the actual job
# list lives on the cross-origin board below — we crawl that board directly.
# The board listing already carries title / department / location / workplace
# inline; each job's Ashby detail page holds the full JD + compensation.
RHODA_BOARD_URL = "https://jobs.ashbyhq.com/rhoda-ai"
ASHBY_HOST = "https://jobs.ashbyhq.com"


def position_crawler() -> List[Dict]:
    positions: List[Dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(RHODA_BOARD_URL, timeout=40000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except TimeoutError:
            pass
        page.wait_for_timeout(2500)

        # 1️⃣ 채용 공고 목록 수집 (Ashby 보드의 UUID 상세 링크만)
        jobs = page.evaluate(r"""
            () => {
                const links = document.querySelectorAll('a[href*="/rhoda-ai/"]');
                const seen = new Set();
                const out = [];
                links.forEach(a => {
                    const href = a.getAttribute('href') || '';
                    // UUID 패턴 상세 페이지만 (목록/필터 링크 제외)
                    if (!/\/rhoda-ai\/[a-f0-9-]{36}$/.test(href) || seen.has(href)) return;
                    seen.add(href);
                    const h3 = a.querySelector('h3');
                    const p = a.querySelector('p');
                    out.push({
                        href: href,
                        title: h3 ? h3.innerText.trim() : '',
                        meta: p ? p.innerText.trim() : '',
                    });
                });
                return out;
            }
        """)

        print(f"[INFO] Found {len(jobs)} job postings")

        # 2️⃣ 각 공고의 Ashby 상세 페이지에서 JD/보상 추출
        for idx, job in enumerate(jobs):
            title = job["title"]
            href = job["href"]
            if not title:
                continue
            full_url = f"{ASHBY_HOST}{href}"

            # 목록 메타라인: "Department • Location • Full time • On-site"
            parts = [s.strip() for s in (job["meta"] or "").split("•") if s.strip()]
            department = parts[0] if len(parts) > 0 else ""
            list_location = parts[1] if len(parts) > 1 else ""
            workplace = parts[3] if len(parts) > 3 else ""

            # Ashby UUID를 안정적인 id로 사용 (제목 중복/location 변동에 견고)
            job_id = href.rstrip("/").split("/")[-1]

            print(f"[INFO] ({idx+1}/{len(jobs)}) Processing: {title}")

            detail = _extract_detail(page, full_url)
            description = detail["description"]
            location = detail["location"] or list_location
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
                "url": full_url,
            })

            time.sleep(0.5)  # polite delay

        browser.close()

    return positions


def _extract_detail(page, full_url, retries=3) -> Dict:
    """Ashby 상세 페이지에서 location / compensation / description 추출."""
    for attempt in range(retries):
        try:
            page.goto(full_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(1200)

            data = page.evaluate(r"""
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
                            h2.innerHTML = '\n\n## ' + h2.innerText + '\n';
                        });
                        clone.querySelectorAll('li').forEach(li => {
                            li.innerHTML = '• ' + li.innerText + '\n';
                        });
                        clone.querySelectorAll('p').forEach(p => {
                            if (p.innerText.trim()) p.innerHTML = p.innerText + '\n';
                        });
                        result.description = clone.innerText.trim();
                    }

                    return result;
                }
            """)

            if data["description"] and len(data["description"]) >= 30:
                return data
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
        print(f"  - {pos['title']} | {pos['department']} | {pos['location']} | {pos['workplace']}")
        print(f"    comp: {pos['compensation']!r}  desc: {len(pos['description'])} chars")
