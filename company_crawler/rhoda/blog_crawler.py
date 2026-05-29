from playwright.sync_api import sync_playwright, TimeoutError
from datetime import datetime
import hashlib
import time

RHODA_URL = "https://www.rhoda.ai"

# Rhoda's "research" stream is currently sourced from the News page only.
# The site keeps research behind a single hard-coded article (no /research
# listing yet), so per request we track /news for now and merge research in
# later by simply appending it here — e.g. ("research", f"{RHODA_URL}/research").
# Both share the same card + article template, so the crawler stays unchanged.
LIST_PAGES = [
    ("news", f"{RHODA_URL}/news"),
]


def blog_crawler():
    """
    Rhoda News(/research) 카드를 수집하고, 내부 글(/news/<slug>)은 상세 페이지에
    재귀적으로 들어가 본문(content)까지 추출한다. 외부 기사(Bloomberg 등)는
    본문을 가져올 수 없으므로 목록의 제목/날짜/출처만 추적한다.

    카드 구조(div.news-card):
        span.badge-source  -> 출처/카테고리 ("Bloomberg", "Press Release")
        h3 > a[href]       -> 제목 + 링크 (내부 /news/<slug> 또는 외부 http)
        span.news-date     -> "March 10, 2026"
        p.news-excerpt     -> (선택) 발췌
    본문(내부): main 안의 .press-card / .press-copy / #about 텍스트.
    """
    items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1️⃣ 목록에서 카드 수집
        cards = []
        for section, url in LIST_PAGES:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            found = page.eval_on_selector_all(
                "div.news-card",
                r"""els => els.map(card => {
                    const a = card.querySelector('h3 a, a');
                    const source = card.querySelector('.badge-source');
                    const date = card.querySelector('.news-date');
                    const excerpt = card.querySelector('.news-excerpt');
                    return {
                        href: a ? a.getAttribute('href') : '',
                        title: a ? a.innerText.replace(/↗/g, '').trim() : '',
                        category: source ? source.innerText.trim() : '',
                        date_raw: date ? date.innerText.trim() : '',
                        excerpt: excerpt ? excerpt.innerText.trim() : '',
                    };
                })""",
            )

            for f in found:
                if not f["href"] or not f["title"]:
                    continue
                cards.append({"section": section, **f})

        # href 기준 dedupe
        seen = set()
        parsed = []
        for card in cards:
            href = card["href"]
            if href in seen:
                continue
            seen.add(href)
            parsed.append(card)

        print(f"[INFO] Found {len(parsed)} news/research posts "
              f"({sum(_is_internal(c['href']) for c in parsed)} internal, "
              f"{sum(not _is_internal(c['href']) for c in parsed)} external)")

        # 2️⃣ 내부 글은 상세 페이지에서 본문 추출, 외부는 발췌만
        for idx, card in enumerate(parsed):
            title = card["title"]
            href = card["href"]
            internal = _is_internal(href)
            url = href if href.startswith("http") else f"{RHODA_URL}{href}"

            content = ""
            if internal:
                print(f"[INFO] ({idx+1}/{len(parsed)}) Fetching body: {title}")
                content = _extract_article_body(page, url)
                if not content:
                    print(f"[WARN] Empty body: {title}")
                time.sleep(0.5)
            else:
                print(f"[INFO] ({idx+1}/{len(parsed)}) External (no body): {title}")

            excerpt = card.get("excerpt", "") or (content[:280].strip() if content else "")

            items.append({
                "id": href,
                "title": title,
                "date": _normalize_date(card["date_raw"]),
                "category": card["category"],
                "type": _type_of(card["category"]),
                "excerpt": excerpt,
                "content": content,
                "content_hash": _hash_text(content),
                "url": url,
            })

        browser.close()

    return items


def _is_internal(href):
    """내부 글(본문 크롤 가능)인지 판별."""
    if not href:
        return False
    if href.startswith("/"):
        return True
    return "rhoda.ai" in href


def _extract_article_body(page, url, retries=3):
    """상세 페이지 본문 추출. press 템플릿(.press-card/.press-copy/#about) 우선."""
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            body = page.evaluate(r"""
                () => {
                    const sels = ['.press-card', '.press-copy', '#about', 'article'];
                    for (const sel of sels) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length >= 30) {
                            return el.innerText.trim();
                        }
                    }
                    // 폴백: main에서 네비 라인 제거
                    const main = document.querySelector('main');
                    if (!main) return '';
                    const navWords = new Set(['Home','Research','News','Team','Careers','Contact']);
                    return main.innerText.split('\n')
                        .filter(l => !navWords.has(l.trim()))
                        .join('\n').trim();
                }
            """)

            if body and len(body) >= 30:
                return body

        except TimeoutError:
            print(f"[WARN] Attempt {attempt+1}/{retries} timeout for {url}")
        except Exception as e:
            print(f"[WARN] Attempt {attempt+1}/{retries} error: {e}")

    return ""


def _type_of(category):
    c = (category or "").lower()
    if "research" in c:
        return "research"
    return "news"


def _normalize_date(date_str):
    """'March 10, 2026' / 'Mar 10, 2026' -> '2026-03-10'."""
    if not date_str:
        return ""
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
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
        print(f"  - [{item['type']}] {item['title']} ({item['date']}) | src={item['category']}")
        print(f"    URL: {item['url']}")
        print(f"    body: {len(item['content'])} chars")
