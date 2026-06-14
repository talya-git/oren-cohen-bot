"""
התחברות אוטומטית לשכל CRM באמצעות פרופיל דפדפן קיים.

האתר מזהה את הדפדפן כ"מכשיר מוכר" ולא מבקש 2FA.
משתמש ב-persistent context עם תיקיית session_data.

הרצה ראשונה (עם דפדפן גלוי - כדי לאמת פעם אחת):
    python scraper/login_with_2fa.py --setup

הרצות הבאות (headless - אוטומטי לגמרי):
    python scraper/login_with_2fa.py
"""

import os
import sys
import json
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

SEHEL_URL = "https://crm.sehel.co.il"
USERNAME = os.getenv("SEHEL_USER", "tsalyato@orencohengroup.com")
PASSWORD = os.getenv("SEHEL_PASS", "YBpB23rM")

SESSION_DIR = Path(__file__).resolve().parent / "session_data"
SESSION_DIR.mkdir(exist_ok=True)
STATE_FILE = SESSION_DIR / "state.json"


def login_and_save_session(headless=True):
    """מתחבר לשכל עם persistent context (כמו דפדפן אמיתי)."""
    with sync_playwright() as p:
        # persistent context - שומר cookies בדיוק כמו דפדפן רגיל
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=headless,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            accept_downloads=True,
            channel="chrome" if not headless else None,
        )
        page = context.new_page()

        print("[1] נכנס לשכל...")
        page.goto(SEHEL_URL, timeout=60000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        # אם כבר מחוברים מ-session קודם
        if "/login" not in page.url:
            print("✓ כבר מחובר (המכשיר מוכר)!")
            state = context.storage_state()
            json.dump(state, open(str(STATE_FILE), "w"))
            context.close()
            return True

        # מילוי שם משתמש + סיסמה
        print("[2] ממלא פרטי התחברות...")
        page.fill('input[name="username"]', USERNAME)
        page.fill('input[name="password"]', PASSWORD)
        time.sleep(1)
        page.click('button[type="submit"]')
        page.wait_for_load_state("domcontentloaded")
        time.sleep(5)

        # בודק אם האתר מבקש קוד וואטסאפ
        login_code_input = page.query_selector('input[name="loginCode"]')
        if login_code_input and login_code_input.is_visible():
            if headless:
                print("⚠ האתר מבקש קוד וואטסאפ.")
                print("  הריצי פעם אחת עם --setup כדי לאמת את המכשיר:")
                print("  python scraper/login_with_2fa.py --setup")
                context.close()
                return False

            # מצב setup - ממתין להזנה ידנית בחלון הדפדפן
            print("\n📱 קוד כניסה נשלח לוואטסאפ!")
            print("   הזיני את הקוד בחלון הדפדפן שנפתח...")
            print("   (ממתין עד 2 דקות)")

            for _ in range(120):
                time.sleep(1)
                if "/login" not in page.url:
                    break

        time.sleep(3)

        if "/login" not in page.url:
            print("✓ התחברות הצליחה! שומר session...")
            state = context.storage_state()
            json.dump(state, open(str(STATE_FILE), "w"))
            context.close()
            return True
        else:
            print("❌ ההתחברות נכשלה")
            page.screenshot(path=str(SESSION_DIR / "login_failed.png"))
            context.close()
            return False


if __name__ == "__main__":
    setup_mode = "--setup" in sys.argv
    if setup_mode:
        print("=== מצב הגדרה (דפדפן גלוי) ===")
        print("אחרי שתתחברי פעם אחת, ההרצות הבאות יהיו אוטומטיות.")
    login_and_save_session(headless=not setup_mode)
