import requests
from bs4 import BeautifulSoup

def member_crawler():
    url = "https://www.pi.website"
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    container = soup.select_one("div.grid.grid-cols-2.md\\:grid-cols-3.gap-y-1")
    members = [
        div.text.strip()
        for div in container.find_all("div", recursive=False)
        if "...and growing!" not in div.text
    ]
    return members
    

