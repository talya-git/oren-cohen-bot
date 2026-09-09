"""גירוד פוסטי שישי של פעם מ-orencohengroup.com/he/blog/"""

import sys, json
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://www.orencohengroup.com"


def scrape_all_pages():
    posts, page = [], 1
    while True:
        url = f"{BASE}/he/blog/" if page == 1 else f"{BASE}/he/blog/page/{page}/"
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".blog_item")
        if not items:
            break
        for item in items:
            title_el = item.select_one("h5 a")
            img_el   = item.select_one(".img img")
            title = title_el.get_text(strip=True) if title_el else ""
            link  = title_el["href"] if title_el else ""
            img   = img_el.get("src", "") if img_el else ""
            posts.append({"title": title, "link": link, "image": img})
        # check if next page exists
        if not soup.select_one("a.next"):
            break
        page += 1
    return posts


if __name__ == "__main__":
    posts = scrape_all_pages()
    print(f"נמצאו {len(posts)} פוסטים:\n")
    for i, p in enumerate(posts, 1):
        print(f"{i:3}. {p['title']}")
        print(f"     {p['link']}")
        print(f"     🖼  {p['image']}\n")
    with open("scraper/blog_posts.json", "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    print(f"\nנשמר ל-scraper/blog_posts.json")
