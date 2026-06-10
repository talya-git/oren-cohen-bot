"""
סקריפט Playwright לשליפת מלאי פרויקטים ויד 2 משכל CRM.
מתחבר לאתר, מייצא אקסלים מכל עמוד, ומעדכן את מאגר הנכסים של הבוט.

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
    print("[1/5] מתחבר לשכל...")
    page.goto(SEHEL_URL)
    page.wait_for_load_state("networkidle")
    
    # מחפש שדות login
    page.fill('input[type="email"], input[name="email"], input[name="username"]', USERNAME)
    page.fill('input[type="password"], input[name="password"]', PASSWORD)
    page.click('button[type="submit"], input[type="submit"], .login-btn, .btn-login')
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    print("   ✓ התחברות הצליחה")


def export_section(page, section_name, section_selector):
    """מייצא את כל העמודים של סקשן מסוים."""
    print(f"[*] נכנס ל-{section_name}...")
    
    # לוחץ על הכפתור
    page.click(f'text="{section_name}"')
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    exported_files = []
    page_num = 1
    
    while True:
        print(f"   עמוד {page_num} - מייצא...")
        
        # מחפש כפתור ייצוא
        export_btn = page.query_selector(
            'text="ייצוא", text="יצוא", text="Export", '
            'button:has-text("ייצוא"), button:has-text("יצוא"), '
            'a:has-text("ייצוא"), a:has-text("יצוא"), '
            '.export-btn, [data-action="export"]'
        )
        
        if export_btn:
            # מחכה להורדה
            with page.expect_download() as download_info:
                export_btn.click()
            download = download_info.value
            
            # שומר את הקובץ
            filename = f"{section_name}_page_{page_num}.xlsx"
            filepath = DOWNLOAD_DIR / filename
            download.save_as(str(filepath))
            exported_files.append(str(filepath))
            print(f"   ✓ נשמר: {filename}")
        else:
            print(f"   ⚠ לא נמצא כפתור ייצוא בעמוד {page_num}")
        
        # בודק אם יש עמוד הבא
        next_btn = page.query_selector(
            'text="הבא", text="Next", text="›", text="»", '
            '.next-page, .pagination-next, '
            'a:has-text("הבא"), button:has-text("הבא"), '
            '[aria-label="Next"], .page-next'
        )
        
        if next_btn and next_btn.is_visible() and next_btn.is_enabled():
            next_btn.click()
            page.wait_for_load_state("networkidle")
            time.sleep(2)
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
        
        # שורה ראשונה = כותרות
        headers = [str(h).strip() if h else "" for h in rows[0]]
        
        for row in rows[1:]:
            if not row[0]:
                continue
            
            record = dict(zip(headers, row))
            
            # מנסה לחלץ שדות רלוונטיים
            prop = {
                "project": record.get("פרויקט", record.get("project", "")),
                "building": record.get("בניין", record.get("building", "")),
                "unit": record.get("מספר נכס", record.get("unit", "")),
                "type": record.get("סוג נכס", record.get("type", "")),
                "floor": record.get("קומה", record.get("floor", "")),
                "rooms": record.get("חדרים", record.get("rooms", "")),
                "size_sqm": record.get("שטח בנוי", record.get("size", "")),
                "extra_sqm": record.get("שטח נוסף", record.get("extra", "")),
                "price": record.get("מחיר שיווק", record.get("price", 0)),
                "status": record.get("סטטוס", record.get("status", "")),
            }
            
            # מסנן נכסים שנמכרו או ללא מחיר
            if "SOLD" in str(record.get("דגם נכס", "")):
                continue
            if not prop["price"] or prop["price"] == 0:
                continue
            
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
        browser = p.chromium.launch(headless=False)  # headless=True לריצה בלי חלון
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        
        # התחברות
        login(page)
        
        # ייצוא מלאי פרויקטים
        print("\n[2/5] מייצא מלאי פרויקטים...")
        project_files = export_section(page, "מלאי פרויקטים", None)
        
        # חזרה לדף הבית
        print("\n[3/5] חוזר לדף הבית...")
        page.goto(SEHEL_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        
        # ייצוא מלאי יד 2
        print("\n[4/5] מייצא מלאי יד 2...")
        yad2_files = export_section(page, "מלאי יד 2", None)
        
        browser.close()
    
    # עיבוד כל האקסלים
    print("\n[5/5] מעבד קבצים...")
    all_files = project_files + yad2_files
    
    if all_files:
        properties = parse_excel_files(all_files)
        update_bot_database(properties)
    else:
        print("⚠ לא הורדו קבצים. בדקי את ה-selectors.")
    
    print("\n🎉 סיום!")


if __name__ == "__main__":
    main()
