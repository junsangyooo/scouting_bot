import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict

SKILD_URL = "https://www.skild.ai"

def parse_date(raw: str) -> str:
    """
    Example:
    'By Skild AI Team • Jan 12, 2026'
    'By Skild AI Team • 24 Sep, 2025'
    """
    date_part = raw.split("•")[-1].strip()
    for fmt in ("%b %d, %Y", "%d %b, %Y", "%d %B, %Y"):
        try:
            return datetime.strptime(date_part, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""

def blog_crawler():
    url = "https://www.skild.ai/blogs"
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    blogs: List[Dict] = []
    featured = soup.select_one("div.featured-content")

    # =====================
    # Featured post
    # =====================
    if featured:
        title_el = featured.find("h2")
        meta_el = featured.find("p")
        link_el = featured.find("a", href=True)

        if title_el and meta_el and link_el:
            href = link_el["href"]
            blogs.append(
                {
                    "id": href,
                    "title": title_el.get_text(strip=True),
                    "date": parse_date(meta_el.get_text(strip=True)),
                    "type": "blog",
                    "excerpt": "",
                    "url": f"{SKILD_URL}{href}",
                }
            )

    # =====================
    # Regular posts
    # =====================
    regular_posts = soup.select("div.regular-posts a.regular-post")
    for post in regular_posts:
        href = post.get("href")
        title_el = post.find("h3")
        meta_el = post.find("p")

        if not (href and title_el and meta_el):
            continue

        blogs.append(
            {
                "id": href,
                "title": title_el.get_text(strip=True),
                "date": parse_date(meta_el.get_text(strip=True)),
                "type": "blog",
                "excerpt": "",
                "url": f"{SKILD_URL}{href}",
            }
        )

    return blogs
