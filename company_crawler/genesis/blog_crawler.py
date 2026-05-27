from playwright.sync_api import sync_playwright, TimeoutError
from datetime import datetime
import hashlib
import time

GENESIS_URL = "https://www.genesis.ai"

# Genesis splits long-form writing across two list pages that share an
# identical card + article template:
#   /blog  -> research/engineering posts
#   /press -> news / press releases
# 사용자 요청대로 둘을 하나의 "blog" 스트림으로 합쳐 추적한다.
LIST_PAGES = [
    ("blog", f"{GENESIS_URL}/blog"),
    ("press", f"{GENESIS_URL}/press"),
]


def blog_crawler():
    """
    Genesis /blog + /press 카드를 수집하고, 각 글의 상세 페이지에 재귀적으로
    들어가 본문(content)까지 추출한다.

    카드 라인 형식: ["May 7, 2026", "Research", "GENE-26.5: ..."]
                  -> [date, category, title...]
    본문 구조: section.article-block > .card > .blocks (div.block 들) + p.description
    """
    items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1️⃣ blog/press 목록에서 카드 수집
        cards = []
        for section, url in LIST_PAGES:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            found = page.eval_on_selector_all(
                'a[href^="/blog/"], a[href^="/press/"]',
                """els => els.map(a => ({
                    href: a.getAttribute('href') || '',
                    lines: (a.innerText || '')
                        .split('\\n')
                        .map(l => l.trim())
                        .filter(Boolean),
                }))""",
            )

            for f in found:
                href = f["href"]
                lines = f["lines"]
                # 네비/푸터의 단순 "/blog", "/press" 링크 및 메타 없는 카드 제외
                if not href or len(lines) < 2:
                    continue
                cards.append({"section": section, "href": href, "lines": lines})

        # href 기준 dedupe
        seen = set()
        parsed = []
        for card in cards:
            href = card["href"]
            if href in seen:
                continue
            seen.add(href)

            lines = card["lines"]
            date_raw = lines[0]
            category = lines[1] if len(lines) > 2 else ""
            title = " ".join(lines[2:]) if len(lines) > 2 else lines[-1]

            parsed.append({
                "section": card["section"],
                "href": href,
                "title": title,
                "category": category,
                "date_raw": date_raw,
                "url": f"{GENESIS_URL}{href}",
            })

        print(f"[INFO] Found {len(parsed)} blog/press posts "
              f"({sum(c['section'] == 'blog' for c in parsed)} blog, "
              f"{sum(c['section'] == 'press' for c in parsed)} press)")

        # 2️⃣ 각 글 상세 페이지에서 본문 추출
        for idx, card in enumerate(parsed):
            title = card["title"]
            print(f"[INFO] ({idx+1}/{len(parsed)}) Fetching body: {title}")

            content = _extract_article_body(page, card["url"])
            if not content:
                print(f"[WARN] Empty body: {title}")
            time.sleep(0.5)

            excerpt = content[:280].strip() if content else ""

            items.append({
                "id": card["href"],
                "title": title,
                "date": _normalize_date(card["date_raw"]),
                "category": card["category"],
                "type": _type_of(card["category"], card["section"]),
                "excerpt": excerpt,
                "content": content,
                "content_hash": _hash_text(content),
                "url": card["url"],
            })

        browser.close()

    return items


def _extract_article_body(page, url, retries=3):
    """상세 페이지 본문을 추출.

    section.article-block 안의 p.description(서브타이틀) + .blocks(본문) 텍스트를
    합쳐서 반환한다. 헤더/푸터/Related 섹션은 자연스럽게 제외된다.
    """
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            body = page.evaluate("""
                () => {
                    const article = document.querySelector('.article-block');
                    if (!article) {
                        const main = document.querySelector('main');
                        return main ? main.innerText.trim() : '';
                    }
                    const parts = [];
                    const desc = article.querySelector('p.description');
                    if (desc && desc.innerText.trim()) parts.push(desc.innerText.trim());
                    const blocks = article.querySelector('.blocks');
                    if (blocks && blocks.innerText.trim()) parts.push(blocks.innerText.trim());
                    return parts.length ? parts.join('\\n\\n') : article.innerText.trim();
                }
            """)

            if body and len(body) >= 30:
                return body

        except TimeoutError:
            print(f"[WARN] Attempt {attempt+1}/{retries} timeout for {url}")
        except Exception as e:
            print(f"[WARN] Attempt {attempt+1}/{retries} error: {e}")

    return ""


def _type_of(category, section):
    c = (category or "").lower()
    if c == "research":
        return "research"
    if c == "news":
        return "news"
    return section  # "blog" or "press"


def _normalize_date(date_str):
    """'May 7, 2026' / 'Mar 11, 2026' -> '2026-05-07'."""
    if not date_str:
        return ""
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def _hash_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


if __name__ == "__main__":
    data = blog_crawler()
    print(f"\n[RESULT] Total {len(data)} posts:\n")
    for item in data:
        print(f"  - [{item['type']}] {item['title']} ({item['date']})")
        print(f"    URL: {item['url']}")
        print(f"    body: {len(item['content'])} chars")
