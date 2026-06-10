"""
סקריפט Playwright לשליפת מלאי פרויקטים ויד 2 משכל CRM.

הרצה: python scraper/scrape_sehel.py
דרישות: pip install playwright openpyxl
         playwright install chromium
"""

import json
import os
import time
import glob
from pathlib import Path

from playwright.sync_api import sync_playwright

# === הגדרות ===
SEHEL_URL = "https://crm.sehel.co.il"
USERNAME = os.getenv("SEHEL_USER", "tsalyato@orencohengroup.com")
PASSWORD = os.getenv("SEHEL_PASS", "YBpB23rM")
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"
PROPERTIES_FILE = Path(__file__).resolve().parent.parent / "data" / "properties.json"


def login(page):
    """התחברות לשכל."""
    print("[1] מתחבר לשכל...")
    page.goto(SEHEL_URL, timeout=60000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(5)

    # דף הלוגין - ממלא שדות
    page.fill('input[type="email"], input[type="text"]', USERNAME)
    page.fill('input[type="password"]', PASSWORD)
    time.sleep(1)

    # לחיצה על כפתור "כניסה"
    page.click('button:has-text("כניסה")')
    time.sleep(5)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)
    print("   ✓ התחברות הצליחה")


def export_all_pages(page, section_name):
    """מייצא אקסל מכל עמוד בסקשן."""
    exported_files = []
    page_num = 1

    while True:
        print(f"   עמוד {page_num} - מייצא...")

        # לוחץ על "יצוא לאקסל" (כפתור בצד שמאל למעלה)
        export_btn = page.query_selector('button:has-text("יצוא לאקסל"), a:has-text("יצוא לאקסל"), :text("יצוא לאקסל")')

        if export_btn:
            with page.expect_download(timeout=30000) as download_info:
                export_btn.click()
            download = download_info.value
            filename = f"{section_name}_page_{page_num}.xlsx"
            filepath = DOWNLOAD_DIR / filename
            download.save_as(str(filepath))
            exported_files.append(str(filepath))
            print(f"   ✓ נשמר: {filename}")
        else:
            print(f"   ⚠ לא נמצא כפתור 'יצוא לאקסל'")
            # מנסה screenshot לדיבאג
            page.screenshot(path=str(DOWNLOAD_DIR / f"debug_{section_name}_{page_num}.png"))

        # בודק אם יש כפתור "הבא" (pagination למעלה)
        next_btn = page.query_selector('button:has-text("הבא"), a:has-text("הבא")')

        if next_btn and next_btn.is_visible() and next_btn.is_enabled():
            next_btn.click()
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)
            page_num += 1
        else:
            print(f"   סה\"כ {page_num} עמודים ב-{section_name}")
            break

    return exported_files


def parse_excel_files(files):
    """קורא את כל האקסלים ומחזיר רשימת נכסים."""
    import openpyxl

    all_properties = []

    for filepath in files:
        if not os.path.exists(filepath):
            continue

        wb = openpyxl.load_workbook(filepath)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 2:
            continue

        # מוצא שורת כותרות (שורה ראשונה או שנייה)
        header_row = 0
        for i, row in enumerate(rows):
            if row and "פרויקט" in str(row):
                header_row = i
                break

        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[header_row])]

        for row in rows[header_row + 1:]:
            if not row or not row[0]:
                continue

            record = {}
            for i, val in enumerate(row):
                if i < len(headers):
                    record[headers[i]] = val

            # מחלץ שדות
            prop = {
                "project": record.get("פרויקט", ""),
                "building": record.get("בניין", ""),
                "unit": record.get("מספר נכס", ""),
                "type": record.get("סוג נכס", ""),
                "model": record.get("דגם", record.get("דגם נכס", "")),
                "floor": record.get("קומה", ""),
                "rooms": record.get("חדרים", ""),
                "size_sqm": record.get("שטח בנוי", ""),
                "extra_sqm": record.get("שטח נוסף", ""),
                "price": record.get("מחיר שיווק", record.get("מחיר", 0)),
                "closing_price": record.get("מחיר סגירה", record.get("מחיר למ\"ת סגירה", "")),
                "status": record.get("סטטוס", ""),
                "buyer": record.get("שם הרוכש", ""),
            }

            # מסנן נכסים שנמכרו
            if "SOLD" in str(prop.get("model", "")):
                continue
            if prop.get("buyer"):
                continue

            # מסנן ללא מחיר
            try:
                price = float(str(prop["price"]).replace(",", ""))
                if price == 0:
                    continue
                prop["price"] = int(price)
            except (ValueError, TypeError):
                continue

            # ניקוי שדה buyer - לא שומרים מידע רגיש
            prop.pop("buyer", None)
            prop.pop("closing_price", None)

            all_properties.append(prop)

    return all_properties


def update_bot_database(properties):
    """מעדכן את קובץ ה-JSON של הבוט."""
    PROPERTIES_FILE.parent.mkdir(exist_ok=True)
    PROPERTIES_FILE.write_text(
        json.dumps(properties, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n[✓] מאגר הבוט עודכן — {len(properties)} נכסים זמינים")


def main():
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    # ניקוי קבצים ישנים
    for f in glob.glob(str(DOWNLOAD_DIR / "*.xlsx")):
        os.remove(f)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # התחברות
        login(page)

        # screenshot לדיבאג — לראות איך הדף נראה אחרי לוגין
        page.screenshot(path=str(DOWNLOAD_DIR / "after_login.png"))
        print("   URL אחרי לוגין:", page.url)

        # === מלאי פרויקטים ===
        print("\n[2] נכנס למלאי פרויקטים...")
        # מנסה כמה selectors
        try:
            page.click('text=מלאי פרויקטים', timeout=10000)
        except:
            try:
                page.click('a >> text=מלאי', timeout=10000)
            except:
                # ניסיון ישיר דרך URL
                page.goto(SEHEL_URL + '/projects-inventory', timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        project_files = export_all_pages(page, "projects")

        # === מלאי יד 2 ===
        print("\n[3] נכנס למלאי דירות יד 2...")
        # חוזר לדף הבית קודם
        page.goto(SEHEL_URL)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        # בתפריט העליון - "מלאי דירות יד 2"
        try:
            page.click('text=מלאי דירות יד', timeout=10000)
        except:
            try:
                page.click('a >> text=יד 2', timeout=10000)
            except:
                page.goto(SEHEL_URL + '/yad2-inventory', timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        yad2_files = export_all_pages(page, "yad2")

        browser.close()

    # עיבוד כל האקסלים
    print("\n[4] מעבד קבצים...")
    all_files = project_files + yad2_files

    if all_files:
        properties = parse_excel_files(all_files)
        update_bot_database(properties)

        # Push to git if possible
        print("\n[5] מעלה לגיט...")
        os.system(f'cd "{PROPERTIES_FILE.parent.parent}" && git add data/properties.json && git commit -m "Auto-update properties" && git push origin main')
    else:
        print("⚠ לא הורדו קבצים.")
        print("   בדקי את צילומי המסך בתיקיית downloads")

    print("\n🎉 סיום!")


if __name__ == "__main__":
    main()
