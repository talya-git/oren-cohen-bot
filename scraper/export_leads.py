"""
מושך את כל הלידים משכל ושומר לאקסל.
הרצה: python scraper/export_leads.py
"""

import requests
import openpyxl
from pathlib import Path
from html.parser import HTMLParser

SEHEL_URL = "https://crm.sehel.co.il"
USERNAME = "tsalyato@orencohengroup.com"
PASSWORD = "YBpB23rM"
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
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # התחברות
    print("מתחבר לשכל...")
    r = session.post(f"{SEHEL_URL}/login", data={"username": USERNAME, "password": PASSWORD})
    if "logout" not in r.text and r.status_code != 200:
        print("שגיאה בהתחברות")
        return

    # שליפת כל הלידים
    print("שולף לידים...")
    all_leads = []
    start = 0
    page_size = 500

    while True:
        r = session.post(f"{SEHEL_URL}/api/clientsServerSide", data={
            "draw": 1, "start": start, "length": page_size
        })
        data = r.json()
        page = data.get("data", [])
        all_leads.extend(page)
        print(f"  {len(all_leads)} לידים...")
        if len(page) < page_size:
            break
        start += page_size

    print(f"סה\"כ {len(all_leads)} לידים. שומר לאקסל...")

    # שמירה לאקסל
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "לידים"

    headers = ["שם", "טלפון 1", "טלפון 2", "מייל", "פרויקט", "סוכן", "תאריך יצירה"]
    ws.append(headers)

    for lead in all_leads:
        project_html = lead.get("projectNameHtml", "")
        ws.append([
            strip_html(lead.get("nameHtml", "") or lead.get("name1", "")),
            lead.get("phone1", ""),
            lead.get("phone2", ""),
            lead.get("email1", ""),
            strip_html(project_html).split("|")[0].strip(),
            strip_html(project_html).split("|")[1].strip() if "|" in strip_html(project_html) else "",
            lead.get("createDate", ""),
        ])

    wb.save(OUTPUT_FILE)
    print(f"✓ נשמר: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
