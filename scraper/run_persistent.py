"""
סקריפט שמשאיר דפדפן פתוח 24 שעות.

- מתחבר פעם אחת בבוקר (עם setup אם צריך)
- משאיר את הדפדפן פתוח
- כל 25 דקות עושה פעולת keepalive (ניווט בתוך האתר)
- כל 30 דקות עושה סקרייפינג (ייצוא אקסל)
- אחרי 24 שעות - סוגר ופותח מחדש

הרצה: python scraper/run_persistent.py
הרצה ראשונה (עם דפדפן גלוי): python scraper/run_persistent.py --setup
"""

import os
import sys
import json
import time
import glob
from pathlib import Path
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

SEHEL_URL = "https://crm.sehel.co.il"
USERNAME = os.getenv("SEHEL_USER", "tsalyato@orencohengroup.com")
PASSWORD = os.getenv("SEHEL_PASS", "YBpB23rM")
SESSION_DIR = Path(__file__).resolve().parent / "session_data"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"
PROPERTIES_FILE = Path(__file__).resolve().parent.parent / "data" / "properties.json"

SCRAPE_INTERVAL = 30 * 60       # 30 דקות בין סקרייפים
KEEPALIVE_INTERVAL = 3 * 60     # 3 דקות בין keepalive
SESSION_LIFETIME = 24 * 60 * 60  # 24 שעות - אז מתחבר מחדש


def login(page, headless=True):
    """התחברות לשכל."""
    print(f"[{now()}] מתחבר לשכל...")
    page.goto(SEHEL_URL, timeout=60000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)

    if "/login" not in page.url:
        print(f"[{now()}] ✓ כבר מחובר!")
        return True

    page.fill('input[name="username"]', USERNAME)
    page.fill('input[name="password"]', PASSWORD)
    time.sleep(1)
    page.click('button[type="submit"]')
    page.wait_for_load_state("domcontentloaded")
    time.sleep(5)

    # בדיקה אם מבקש קוד וואטסאפ
    login_code_input = page.query_selector('input[name="loginCode"]')
    if login_code_input and login_code_input.is_visible():
        if headless:
            print(f"[{now()}] ⚠ האתר מבקש קוד וואטסאפ!")
            print(f"   הריצי: python scraper/run_persistent.py --setup")
            return False

        print(f"[{now()}] 📱 קוד נשלח לוואטסאפ! הזיני בחלון הדפדפן...")
        for _ in range(120):
            time.sleep(1)
            if "/login" not in page.url:
                break

    time.sleep(3)
    if "/login" not in page.url:
        print(f"[{now()}] ✓ התחברות הצליחה!")
        return True
    else:
        print(f"[{now()}] ❌ התחברות נכשלה")
        return False


def keepalive(page):
    """פעולת keepalive - מנווט בין דפים כדי שה-session לא יפוג."""
    import random
    pages = [
        '/projects/app/listing',
        '/projects/app/listing/yad2',
        '/projects/app/dashboard',
        '/projects/app/listing',
    ]
    try:
        target = random.choice(pages)
        page.goto(SEHEL_URL + target, timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(random.uniform(1, 3))

        # בודק שעדיין מחובר
        if "/login" in page.url:
            print(f"[{now()}] ⚠ Session פג! צריך login מחדש")
            return False

        # סקרול קצת בדף
        page.mouse.wheel(0, random.randint(100, 300))
        time.sleep(random.uniform(0.5, 1.5))

        print(f"[{now()}] ♻ keepalive OK ({target})")
        return True
    except Exception as e:
        print(f"[{now()}] ⚠ keepalive שגיאה: {e}")
        return False


def scrape(page):
    """סקרייפינג - ייצוא אקסל מכל הדפים."""
    import openpyxl

    DOWNLOAD_DIR.mkdir(exist_ok=True)
    for f in glob.glob(str(DOWNLOAD_DIR / "*.xlsx")):
        os.remove(f)

    all_files = []

    # מלאי פרויקטים
    print(f"[{now()}] מייצא מלאי פרויקטים...")
    page.goto(SEHEL_URL + '/projects/app/listing', timeout=60000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)

    if "/login" in page.url:
        print(f"[{now()}] ⚠ לא מחובר!")
        return False

    all_files += export_all_pages(page, "projects")

    # מלאי יד 2
    print(f"[{now()}] מייצא מלאי יד 2...")
    page.goto(SEHEL_URL + '/projects/app/listing/yad2', timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)
    all_files += export_all_pages(page, "yad2")

    # עיבוד
    if all_files:
        properties = parse_excel_files(all_files)
        PROPERTIES_FILE.parent.mkdir(exist_ok=True)
        PROPERTIES_FILE.write_text(
            json.dumps(properties, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[{now()}] ✓ עודכנו {len(properties)} נכסים")

        # Push to git
        os.system(f'cd "{PROPERTIES_FILE.parent.parent}" && git add -A && git commit -m "Auto-update properties" && git push origin main 2>nul')
        return True
    else:
        print(f"[{now()}] ⚠ לא הורדו קבצים")
        return False


def export_all_pages(page, section_name):
    """מייצא אקסל מכל עמוד."""
    exported_files = []
    page_num = 1

    while True:
        export_btn = None
        for selector in [
            'text="יצוא לאקסל"', 'button:has-text("יצוא")',
            'a:has-text("יצוא")', '[class*="export"]',
        ]:
            export_btn = page.query_selector(selector)
            if export_btn and export_btn.is_visible():
                break
            export_btn = None

        if not export_btn:
            for el in page.query_selector_all('button, a, span, input'):
                try:
                    if 'יצוא' in el.inner_text() and 'אקסל' in el.inner_text():
                        export_btn = el
                        break
                except:
                    continue

        if export_btn:
            try:
                with page.expect_download(timeout=30000) as download_info:
                    export_btn.click()
                download = download_info.value
                filename = f"{section_name}_page_{page_num}.xlsx"
                filepath = DOWNLOAD_DIR / filename
                download.save_as(str(filepath))
                exported_files.append(str(filepath))
            except:
                pass

        next_btn = page.query_selector('button:has-text("הבא"), a:has-text("הבא")')
        if next_btn and next_btn.is_visible() and next_btn.is_enabled():
            next_btn.click()
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)
            page_num += 1
        else:
            break

    return exported_files


def parse_excel_files(files):
    """קורא אקסלים ומחזיר רשימת נכסים."""
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

        header_row = 0
        for i, row in enumerate(rows):
            if row and row[0] == "פרויקט":
                header_row = i
                break

        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[header_row])]

        for row in rows[header_row + 1:]:
            if not row or not row[0]:
                continue
            record = {headers[i]: val for i, val in enumerate(row) if i < len(headers)}
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
                "status": record.get("סטטוס", ""),
                "buyer": record.get("שם הרוכש", ""),
            }

            if "SOLD" in str(prop.get("model", "")):
                continue
            if prop.get("buyer"):
                continue
            try:
                price = float(str(prop["price"]).replace(",", ""))
                if price == 0:
                    continue
                prop["price"] = int(price)
            except (ValueError, TypeError):
                continue

            prop.pop("buyer", None)
            all_properties.append(prop)

    return all_properties


def now():
    return datetime.now().strftime("%H:%M:%S")


def main():
    setup_mode = "--setup" in sys.argv
    SESSION_DIR.mkdir(exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    print("=" * 50)
    print("  Sehel Persistent Scraper")
    print(f"  מצב: {'setup (דפדפן גלוי)' if setup_mode else 'אוטומטי (headless)'}")
    print(f"  סקרייפ כל: {SCRAPE_INTERVAL // 60} דקות")
    print(f"  keepalive כל: {KEEPALIVE_INTERVAL // 60} דקות")
    print(f"  login מחדש כל: {SESSION_LIFETIME // 3600} שעות")
    print("  לסגירה: Ctrl+C")
    print("=" * 50)

    while True:
        session_start = time.time()

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                headless=not setup_mode,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                accept_downloads=True,
            )
            page = context.new_page()

            # Login
            if not login(page, headless=not setup_mode):
                context.close()
                if setup_mode:
                    return
                print(f"[{now()}] ממתין 5 דקות ומנסה שוב...")
                time.sleep(300)
                continue

            # אחרי setup מוצלח - עוברים ל-headless
            if setup_mode:
                print(f"[{now()}] ✓ Setup הצליח! מעכשיו ירוץ אוטומטי.")
                setup_mode = False

            # לולאת עבודה - 24 שעות
            last_scrape = 0
            last_keepalive = time.time()

            while time.time() - session_start < SESSION_LIFETIME:
                current_time = time.time()

                # סקרייפינג כל 30 דקות
                if current_time - last_scrape >= SCRAPE_INTERVAL:
                    try:
                        success = scrape(page)
                        if not success:
                            # session פג - יוצא מהלולאה ומתחבר מחדש
                            break
                        last_scrape = current_time
                        last_keepalive = current_time  # סקרייפ = גם keepalive
                    except Exception as e:
                        print(f"[{now()}] ⚠ שגיאת סקרייפ: {e}")

                # keepalive כל 25 דקות (אם לא היה סקרייפ)
                elif current_time - last_keepalive >= KEEPALIVE_INTERVAL:
                    if not keepalive(page):
                        break  # session פג
                    last_keepalive = current_time

                # מונה
                next_scrape = max(0, SCRAPE_INTERVAL - (current_time - last_scrape))
                mins = int(next_scrape) // 60
                secs = int(next_scrape) % 60
                print(f"\r⏳ סקרייפ הבא בעוד: {mins:02d}:{secs:02d}", end="", flush=True)
                time.sleep(10)

            # סוגר את הדפדפן אחרי 24 שעות (או שגיאה)
            print(f"\n[{now()}] סוגר session ומתחבר מחדש...")
            context.close()

        # ממתין דקה לפני reconnect
        time.sleep(60)


if __name__ == "__main__":
    main()
