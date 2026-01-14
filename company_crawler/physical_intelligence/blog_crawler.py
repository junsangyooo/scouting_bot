import requests
from bs4 import BeautifulSoup
from datetime import datetime

def blog_crawler():
    PI_URL = "https://www.pi.website"
    url = "https://www.pi.website/blog"
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    container = soup.select_one("div.relative.flex.flex-col.space-y-4")

    if not container:
        raise RuntimeError("Research container not found")
    
    items = []
    for a in container.find_all("a", recursive=False):
        href = a.get("href")
        if not href:
            continue
        title_el = a.select_one("div.font-semibold")
        date_el = a.select_one("div.text-muted-foreground")
        excerpt_el = a.find("p")

        title = title_el.text.strip() if title_el else ""
        date_raw = date_el.text.strip() if date_el else ""
        excerpt = excerpt_el.text.strip() if excerpt_el else ""

        items.append({
            "id": href,
            "title": title,
            "date": _normalize_date(date_raw),
            "type": "blog" if href.startswith("/blog") else "research",
            "excerpt": excerpt,
            "url": f"{PI_URL}{href}"
        })
    return items

def _normalize_date(date_str):
    """
    'December 22, 2025' -> '2025-12-22'
    """
    try:
        return datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return date_str