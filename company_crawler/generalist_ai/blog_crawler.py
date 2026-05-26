from playwright.sync_api import sync_playwright
from datetime import datetime

GENERALIST_URL = "https://generalistai.com"
BLOG_URL = "https://generalistai.com/blog"


def blog_crawler():
    items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BLOG_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        posts = page.eval_on_selector_all(
            "a.blog-menu-article-link",
            """els => els.map(a => {
                const text = a.innerText.trim();
                const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                return {
                    href: a.getAttribute('href') || '',
                    lines: lines,
                };
            })""",
        )

        browser.close()

    for post in posts:
        href = post["href"]
        lines = post["lines"]
        if not href or len(lines) < 2:
            continue

        title = lines[0]
        date_raw = lines[-1]
        excerpt = "\n".join(lines[1:-1]) if len(lines) > 2 else ""

        items.append({
            "id": href,
            "title": title,
            "date": _normalize_date(date_raw),
            "type": "blog",
            "excerpt": excerpt,
            "url": f"{GENERALIST_URL}{href}",
        })

    return items


def _normalize_date(date_str):
    """'Apr 7, 2026' -> '2026-04-07'"""
    try:
        return datetime.strptime(date_str, "%b %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return date_str
