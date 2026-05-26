from playwright.sync_api import sync_playwright, TimeoutError
from datetime import datetime
import hashlib
import re
import time

SUNDAY_URL = "https://www.sunday.ai"
JOURNAL_URL = f"{SUNDAY_URL}/journal"

# 카드 메타에서 무시할 CTA 텍스트
_CTA_PREFIXES = ("Read article", "Read more")
# "March 13, 2026" / "November 20, 2025" 형태
_DATE_RE = re.compile(r"^[A-Z][a-z]+\s+\d{1,2},\s+\d{4}$")


def blog_crawler():
    """
    Sunday 'Journal' 페이지를 크롤링한다.

    - 내부 글(`/journal/<slug>`)은 상세 페이지에 재귀적으로 들어가 본문(content)까지 수집.
    - 외부 'Stories' 카드(wired.com, youtube.com 등)는 외부 본문은 수집 불가하므로
      제목/카테고리/날짜/외부 URL만 추적한다 (목록에서 누락되지 않도록).
    """
    items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(JOURNAL_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # 1️⃣ 저널 카드 목록 수집 (내부 글 + 외부 Stories)
        cards = page.eval_on_selector_all(
            "article",
            """els => els.map(art => {
                const a = art.closest('a') || art.querySelector('a');
                const h = art.querySelector('h1,h2,h3,h4,h5');
                const lines = [...art.querySelectorAll('p,span')]
                    .map(e => e.innerText.trim())
                    .filter(Boolean);
                return {
                    href: a ? a.getAttribute('href') : null,
                    title: h ? h.innerText.trim() : '',
                    lines: lines,
                };
            })""",
        )

        # href 기준 dedupe (featured hero 카드가 중복으로 잡히는 경우 대비)
        seen = set()
        parsed = []
        for card in cards:
            href = card["href"]
            title = card["title"]
            if not href or not title or href in seen:
                continue
            seen.add(href)

            category, date_raw = _parse_meta(card["lines"])
            is_internal = href.startswith("/journal/")
            url = href if href.startswith("http") else f"{SUNDAY_URL}{href}"

            parsed.append({
                "href": href,
                "title": title,
                "category": category,
                "date_raw": date_raw,
                "is_internal": is_internal,
                "url": url,
            })

        print(f"[INFO] Found {len(parsed)} journal cards "
              f"({sum(c['is_internal'] for c in parsed)} internal, "
              f"{sum(not c['is_internal'] for c in parsed)} external)")

        # 2️⃣ 내부 글은 상세 페이지에서 본문 추출
        for idx, card in enumerate(parsed):
            title = card["title"]
            category = card["category"]
            content = ""

            if card["is_internal"]:
                print(f"[INFO] ({idx+1}/{len(parsed)}) Fetching body: {title}")
                content = _extract_article_body(page, card["url"])
                if not content:
                    print(f"[WARN] Empty body: {title}")
                time.sleep(0.5)
            else:
                print(f"[INFO] ({idx+1}/{len(parsed)}) External story (no body): {title}")

            excerpt = content[:280].strip() if content else ""

            items.append({
                "id": card["href"],
                "title": title,
                "date": _normalize_date(card["date_raw"]),
                "category": category,
                "type": _type_of(category),
                "excerpt": excerpt,
                "content": content,
                "content_hash": _hash_text(content),
                "url": card["url"],
            })

        browser.close()

    return items


def _extract_article_body(page, url, retries=3):
    """저널 상세 페이지에서 본문 컨테이너(p.body-1의 부모)의 텍스트를 추출.

    하단 'Related articles' / 'Recent entries' 캐러셀과 헤더/푸터는 제외된다.
    """
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            body = page.evaluate("""
                () => {
                    const firstBody = document.querySelector('.body-1');
                    if (firstBody && firstBody.parentElement) {
                        return firstBody.parentElement.innerText.trim();
                    }
                    // fallback: main 전체 텍스트
                    const main = document.querySelector('main');
                    return main ? main.innerText.trim() : '';
                }
            """)

            if body and len(body) >= 50:
                return body

        except TimeoutError:
            print(f"[WARN] Attempt {attempt+1}/{retries} timeout for {url}")
        except Exception as e:
            print(f"[WARN] Attempt {attempt+1}/{retries} error: {e}")

    return ""


def _parse_meta(lines):
    """카드 메타 라인에서 (category, date_raw)를 뽑는다.

    예) ["Research", "November 20, 2025", "Read article"] -> ("Research", "November 20, 2025")
        ["March 13, 2026", "Read article"]                -> ("", "March 13, 2026")
    """
    meta = [l for l in lines if not l.startswith(_CTA_PREFIXES)]
    date_raw = ""
    category = ""
    for l in meta:
        if _DATE_RE.match(l):
            date_raw = l
        else:
            category = l
    return category, date_raw


def _type_of(category):
    c = (category or "").lower()
    if c == "research":
        return "research"
    if c == "stories":
        return "story"
    return "journal"


def _normalize_date(date_str):
    """'March 13, 2026' -> '2026-03-13'"""
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return date_str


def _hash_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


if __name__ == "__main__":
    data = blog_crawler()
    print(f"\n[RESULT] Total {len(data)} journal items:\n")
    for item in data:
        print(f"  - [{item['type']}] {item['title']} ({item['date']})")
        print(f"    URL: {item['url']}")
        print(f"    body: {len(item['content'])} chars")
        print()
