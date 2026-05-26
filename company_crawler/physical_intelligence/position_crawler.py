from playwright.sync_api import sync_playwright, TimeoutError
from urllib.parse import quote
import hashlib
import time

JOIN_US_URL = "https://www.pi.website/join-us"

# Ashby iframe에서 제외할 텍스트 (지원 폼 필드 등)
_BLACKLIST = {
    "Apply", "Back", "Apply for this job", "Physical Intelligence",
    "Submit Application", "Powered by",
}
_FORM_FIELDS = {
    "Name", "Email", "Resume", "Upload File", "LinkedIn", "Phone",
    "Personal website or GitHub",
}


def position_crawler():
    """
    PI 채용 페이지 스크래퍼.

    사이트 구조 (2026-04 기준):
      - section > button  : 부서별 아코디언 토글
      - section > ul > li > a[href="?ashby_jid=..."]  : 개별 채용 공고 링크
      - iframe#ashby_embed_iframe  : 클릭 시 로드되는 JD 상세
    """
    positions = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(JOIN_US_URL, timeout=30000)
        page.wait_for_load_state("networkidle")

        # 1️⃣ 모든 부서 섹션을 펼쳐서 job 링크 수집
        jobs = _collect_all_job_links(page)
        print(f"[INFO] Found {len(jobs)} position links")

        # 2️⃣ 각 job 클릭 → iframe에서 JD 추출
        for idx, job in enumerate(jobs):
            title = job["title"]
            ashby_jid = job["ashby_jid"]
            print(f"[INFO] ({idx+1}/{len(jobs)}) Processing: {title}")

            try:
                description = _extract_job_description(page, ashby_jid)
                if not description:
                    print(f"[WARN] Empty JD: {title}")
                    continue

                positions.append({
                    "id": _make_job_id(title),
                    "title": title,
                    "location": "",
                    "compensation": "",
                    "description": description,
                    "description_hash": _hash_text(description),
                    "url": JOIN_US_URL,
                })

            except Exception as e:
                print(f"[ERROR] Failed position {title}: {e}")
                continue

            time.sleep(0.5)

        browser.close()

    return positions


# ---------- internal ----------

def _collect_all_job_links(page):
    """부서별 아코디언을 모두 펼친 뒤, job 링크(title + ashby_jid)를 수집."""
    sections = page.query_selector_all("section")
    all_jobs = []

    for section in sections:
        btn = section.query_selector("button")
        if not btn:
            continue
        expanded = btn.get_attribute("aria-expanded")
        if expanded != "true":
            btn.click()
            page.wait_for_timeout(400)

        links = section.query_selector_all("ul li a")
        for link in links:
            href = link.get_attribute("href") or ""
            title = link.inner_text().strip()
            jid = href.split("ashby_jid=")[-1] if "ashby_jid=" in href else ""
            if title and jid:
                all_jobs.append({"title": title, "ashby_jid": jid})

    return all_jobs


def _extract_job_description(page, ashby_jid, retries=3):
    """ashby_jid로 JD 페이지를 열고 iframe 본문을 추출."""
    url = f"{JOIN_US_URL}?ashby_jid={ashby_jid}"

    for attempt in range(retries):
        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle")

            iframe_el = page.wait_for_selector(
                "iframe#ashby_embed_iframe", state="attached", timeout=15000
            )
            time.sleep(2)

            frame = iframe_el.content_frame()
            if not frame:
                continue

            try:
                frame.wait_for_selector("p, h1, h2", state="visible", timeout=10000)
            except TimeoutError:
                continue

            time.sleep(1)
            raw_text = frame.locator("body").inner_text()

            if not raw_text or len(raw_text.strip()) < 50:
                continue

            return _clean_ashby_text(raw_text)

        except TimeoutError:
            print(f"[WARN] Attempt {attempt+1}/{retries} timeout for {ashby_jid}")
        except Exception as e:
            print(f"[WARN] Attempt {attempt+1}/{retries} error: {e}")

    return ""


# ---------- helpers ----------

def _make_job_id(title: str) -> str:
    return quote(title.lower().replace(" ", "-"))


def _clean_ashby_text(text: str) -> str:
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]

    cleaned = []
    hit_form = False
    for line in lines:
        if line in _BLACKLIST:
            continue
        if line.startswith("Pursuant to"):
            cleaned.append(line)
            hit_form = True
            continue
        if hit_form and line in _FORM_FIELDS:
            continue
        if not hit_form:
            cleaned.append(line)

    return "\n\n".join(cleaned)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
