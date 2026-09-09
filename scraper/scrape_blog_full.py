"""גירוד תוכן מלא של כל פוסט שישי של פעם."""

import sys, json, time, requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_post_content(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # תוכן הפוסט נמצא ב-.blog_detail_content או .entry-content
        content_el = (
            soup.select_one(".blog_detail_content .text-wrapper")
            or soup.select_one(".entry-content")
            or soup.select_one(".elementor-widget-theme-post-content")
            or soup.select_one("article .entry-content")
        )
        if not content_el:
            return ""
        # הסר כפתורי "קרא עוד" וקישורים פנימיים
        for el in content_el.select("a.more-link, a.btn_read_more, button"):
            el.decompose()
        text = content_el.get_text(separator="\n", strip=True)
        # נקה שורות ריקות כפולות
        lines = [l for l in text.splitlines() if l.strip()]
        return "\n".join(lines)
    except Exception as e:
        return f"(שגיאה: {e})"


if __name__ == "__main__":
    with open("scraper/blog_posts.json", encoding="utf-8") as f:
        posts = json.load(f)

    for i, p in enumerate(posts, 1):
        print(f"\r{i}/{len(posts)} — {p['title'][:50]}", end="", flush=True)
        p["content"] = fetch_post_content(p["link"])
        time.sleep(0.3)  # נימוסי — לא להעמיס על השרת

    with open("scraper/blog_posts_full.json", "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

    print(f"\n\n✅ נשמר: scraper/blog_posts_full.json")
