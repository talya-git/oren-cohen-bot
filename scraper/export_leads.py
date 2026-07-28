"""
מושך את כל הלידים משכל ושומר לאקסל.
משתמש ב-session שמור מ-save_session.py
הרצה: python scraper/export_leads.py
"""

import openpyxl
from pathlib import Path
from html.parser import HTMLParser
from playwright.sync_api import sync_playwright

SEHEL_URL = "https://crm.sehel.co.il"
SESSION_DIR = Path(__file__).resolve().parent / "session_data"

# fallback למיקום אלטרנטיבי
if not SESSION_DIR.exists():
    SESSION_DIR = Path(r"C:\Users\Dell\Desktop\oren-cohen-bot\scraper\session_data")
OUTPUT_FILE = Path(__file__).resolve().parent / "leads_export.xlsx"


def strip_html(html):
    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
        def handle_data(self, data):
            t = data.strip()
            if t:
                self.parts.append(t)
    p = P()
    p.feed(html or "")
    return " | ".join(p.parts)


def main():
    if not SESSION_DIR.exists():
        print("❌ אין session שמור. הרץ קודם: python scraper/save_session.py")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = browser.new_page()

        print("מתחבר לשכל...")
        page.goto(SEHEL_URL)
        page.wait_for_load_state("networkidle")
        print(f"  URL נוכחי: {page.url}")

        if "login" in page.url.lower():
            print("❌ Session פג תוקף. הרץ שוב: python scraper/save_session.py")
            browser.close()
            return

        print("✓ מחובר! שולף לידים...")

        all_leads = []
        start = 0
        page_size = 500

        while True:
            response = page.request.post(
                f"{SEHEL_URL}/api/clientsServerSide",
                form={"draw": "1", "start": str(start), "length": str(page_size)}
            )
            if not response.ok:
                print(f"  שגיאה: סטטוס {response.status}")
                break
            data = response.json()
            chunk = data.get("data", [])
            all_leads.extend(chunk)
            print(f"  {len(all_leads)} לידים...")
            if len(chunk) < page_size:
                break
            start += page_size

        browser.close()

    print(f"סה\"כ {len(all_leads)} לידים. שומר לאקסל...")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "לידים"
    ws.append(["שם", "טלפון 1", "טלפון 2", "מייל", "פרויקט", "סוכן", "תאריך יצירה"])

    for lead in all_leads:
        project_html = lead.get("projectNameHtml", "")
        project_clean = strip_html(project_html)
        parts = project_clean.split("|")
        ws.append([
            strip_html(lead.get("nameHtml", "") or lead.get("name1", "")),
            lead.get("phone1", ""),
            lead.get("phone2", ""),
            lead.get("email1", ""),
            parts[0].strip() if parts else "",
            parts[1].strip() if len(parts) > 1 else "",
            lead.get("createDate", ""),
        ])

    wb.save(OUTPUT_FILE)
    print(f"✓ נשמר: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
