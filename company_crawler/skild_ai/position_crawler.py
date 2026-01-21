from playwright.sync_api import sync_playwright, TimeoutError
from typing import List, Dict
import hashlib
import time
import re

SKILD_CAREER_URL = "https://www.skild.ai/career"
JOB_BOARD_URL = "https://job-boards.greenhouse.io/skildai-careers"


def position_crawler():
    positions: List[Dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(JOB_BOARD_URL, timeout=30000)
        page.wait_for_selector("div.job-posts")

        # 모든 부서 블록
        departments = page.query_selector_all(
            "div.job-posts--table--department"
        )

        for dept in departments:
            job_links = dept.query_selector_all("tr.job-post a")

            for link in job_links:
                title_el = link.query_selector("p.body--medium")
                location_el = link.query_selector("p.body__secondary")
                href = link.get_attribute("href")

                if not (title_el and location_el and href):
                    continue

                title = title_el.inner_text().strip()
                location = location_el.inner_text().strip()
                job_id = normalize_id(title + "__" + location)

                # === 상세 페이지 새 탭 열기 ===
                detail_page = browser.new_page()
                detail_page.goto(href, timeout=60_000)
                detail_page.wait_for_selector("div.job__description")

                desc_el = detail_page.query_selector(
                    "div.job__description"
                )
                description = desc_el.inner_text().strip()

                description_hash = hash_text(description)

                positions.append(
                    {
                        "id": job_id,
                        "title": title,
                        "location": location,
                        "compensation": "",
                        "description": description,
                        "description_hash": description_hash,
                    }
                )

                detail_page.close()
                time.sleep(0.3)  # polite delay

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
    print(f"[INFO] Crawled {len(data)} positions")
    for p in data[:3]:
        print(p["title"], "->", p["location"])