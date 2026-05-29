from playwright.sync_api import sync_playwright, TimeoutError
import hashlib
import re
import time

BASE_URL = "https://www.dyna.co"

# dyna.co was rebuilt as a Lovable SPA. Research/company posts now live on two
# pages that share the SAME card markup, so we track both as one "blog" stream
# (mirrors genesis merging /blog + /press). Each card is a router-driven
# `div.group.cursor-pointer` with an <h2>/<h3> title, a `p.hidden.md:block`
# excerpt and a date <span> in "MMM 'YY" form — and NO <a> href (navigation is
# client-side), so we can't capture a per-post URL and link to the listing page.
LIST_PAGES = [
    ("research", f"{BASE_URL}/research"),
    ("blog", f"{BASE_URL}/blog"),
]

_MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def generate_id(title: str, date: str) -> str:
    return hashlib.md5(f"{title}_{date}".encode()).hexdigest()


def parse_date(raw: str) -> str:
    """'JUN 15 '25' -> '2025-06-15'; new 'MMM \\'YY' (no day) -> '2025-06-01'."""
    raw = (raw or "").strip()
    m = re.match(r"([A-Z]{3})\s+(\d{1,2})\s+'(\d{2})", raw)  # MMM DD 'YY (legacy)
    if m:
        mo, da, yy = m.groups()
        return f"20{yy}-{_MONTHS.get(mo, '01')}-{da.zfill(2)}"
    m = re.match(r"([A-Z]{3})\s+'?(\d{2})$", raw)            # MMM 'YY (current)
    if m:
        mo, yy = m.groups()
        return f"20{yy}-{_MONTHS.get(mo, '01')}-01"
    return raw


def blog_crawler():
    results = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for section, url in LIST_PAGES:
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
            except TimeoutError:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)  # SPA cards fade in after load

            cards = page.evaluate(r"""
                () => {
                    const out = [];
                    document.querySelectorAll('div.cursor-pointer').forEach(card => {
                        const h = card.querySelector('h2, h3');
                        if (!h) return;
                        const title = (h.innerText || '').trim();
                        if (!title) return;
                        const p = card.querySelector('p');
                        const excerpt = p ? (p.innerText || '').trim() : '';
                        let date_raw = '';
                        card.querySelectorAll('span').forEach(s => {
                            const t = (s.innerText || '').trim();
                            if (/^[A-Z]{3}\s+(\d{1,2}\s+)?'?\d{2}$/.test(t)) date_raw = t;
                        });
                        out.push({ title, excerpt, date_raw });
                    });
                    return out;
                }
            """)

            print(f"[INFO] {section}: found {len(cards)} cards")

            for c in cards:
                title = c["title"]
                date = parse_date(c["date_raw"])
                item_id = generate_id(title, date)
                if item_id in seen:
                    continue
                seen.add(item_id)
                results.append({
                    "id": item_id,
                    "title": title,
                    "date": date,
                    "type": section,
                    "excerpt": c["excerpt"],
                    "url": url,   # per-post URLs aren't exposed (router-driven cards)
                })

        browser.close()

    print(f"[INFO] Found {len(results)} research/blog posts")
    return results


if __name__ == "__main__":
    data = blog_crawler()
    print(f"\n[RESULT] Total {len(data)} items crawled:\n")
    for item in data:
        print(f"  - [{item['type']}] {item['title']}  ({item['date']})")
        print(f"    {item['excerpt'][:80]}")
