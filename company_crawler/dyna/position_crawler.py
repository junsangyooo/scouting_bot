from playwright.sync_api import sync_playwright
from typing import List, Dict
import hashlib
import time
import re

DYNA_CAREER_URL = "https://jobs.ashbyhq.com/dyna-robotics"


def position_crawler():
    positions: List[Dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(DYNA_CAREER_URL, timeout=30000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # JavaScript로 모든 공고 링크 수집
        job_links = page.evaluate("""
            () => {
                const links = document.querySelectorAll('a.ashby-job-posting-brief-list a, a[href*="/dyna-robotics/"]');
                const results = [];
                const seen = new Set();

                links.forEach(link => {
                    const href = link.getAttribute('href');
                    // UUID 패턴 포함된 링크만 (상세 페이지)
                    if (href && /\\/dyna-robotics\\/[a-f0-9-]{36}$/.test(href) && !seen.has(href)) {
                        seen.add(href);
                        const titleEl = link.querySelector('h3');
                        const detailsEl = link.querySelector('p');
                        results.push({
                            href: href,
                            title: titleEl ? titleEl.innerText.trim() : '',
                            details: detailsEl ? detailsEl.innerText.trim() : ''
                        });
                    }
                });

                return results;
            }
        """)

        print(f"[INFO] Found {len(job_links)} job postings")

        for job in job_links:
            title = job['title']
            href = job['href']
            full_url = f"https://jobs.ashbyhq.com{href}"

            print(f"[INFO] Processing: {title}")

            try:
                # 상세 페이지로 이동
                page.goto(full_url, timeout=30000)
                page.wait_for_load_state("networkidle")
                time.sleep(1)

                # JavaScript로 상세 정보 추출
                detail_data = page.evaluate("""
                    () => {
                        const result = {
                            location: '',
                            compensation: '',
                            description: ''
                        };

                        // Left pane에서 Location, Compensation 추출
                        const sections = document.querySelectorAll('div[class*="section"]');
                        sections.forEach(section => {
                            const heading = section.querySelector('h2');
                            if (heading) {
                                const headingText = heading.innerText.trim().toLowerCase();
                                if (headingText === 'location') {
                                    const content = section.querySelector('p');
                                    if (content) {
                                        result.location = content.innerText.trim();
                                    }
                                } else if (headingText === 'compensation') {
                                    // Compensation은 span._compensationTierSummary에서 가져오기
                                    const compSpan = section.querySelector('span[class*="compensationTierSummary"]');
                                    if (compSpan) {
                                        result.compensation = compSpan.innerText.trim();
                                    } else {
                                        // fallback: 첫 번째 p 태그
                                        const content = section.querySelector('p');
                                        if (content) {
                                            result.compensation = content.innerText.trim();
                                        }
                                    }
                                }
                            }
                        });

                        // Description 추출
                        const descEl = document.querySelector('div[class*="descriptionText"], .ashby-job-posting-description');
                        if (descEl) {
                            // HTML을 읽기 좋은 텍스트로 변환
                            const clone = descEl.cloneNode(true);

                            // h2 태그 앞에 줄바꿈 추가
                            clone.querySelectorAll('h2').forEach(h2 => {
                                h2.innerHTML = '\\n\\n## ' + h2.innerText + '\\n';
                            });

                            // li 태그 앞에 불릿 추가
                            clone.querySelectorAll('li').forEach(li => {
                                li.innerHTML = '• ' + li.innerText + '\\n';
                            });

                            // p 태그 뒤에 줄바꿈
                            clone.querySelectorAll('p').forEach(p => {
                                if (p.innerText.trim()) {
                                    p.innerHTML = p.innerText + '\\n';
                                }
                            });

                            result.description = clone.innerText.trim();
                        }

                        return result;
                    }
                """)

                job_id = normalize_id(title + "__" + detail_data['location'])
                description = detail_data['description']
                description_hash = hash_text(description)

                positions.append({
                    "id": job_id,
                    "title": title,
                    "location": detail_data['location'],
                    "compensation": detail_data['compensation'],
                    "description": description,
                    "description_hash": description_hash
                })

                print(f"[INFO] Collected: {title} | {detail_data['location']} | {detail_data['compensation']}")

            except Exception as e:
                print(f"[ERROR] Failed to process {title}: {e}")
                continue

            time.sleep(0.5)  # polite delay

        browser.close()

    return positions


def normalize_id(title: str) -> str:
    """
    Title -> lowercase, kebab-case id
    """
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    data = position_crawler()
    print(f"\n[RESULT] Crawled {len(data)} positions\n")
    for p in data:
        print(f"  - {p['title']}")
        print(f"    Location: {p['location']}")
        print(f"    Compensation: {p['compensation']}")
        print()
