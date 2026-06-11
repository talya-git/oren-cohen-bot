"""
שלב 1: הרצה ראשונה — התחברות ידנית ושמירת session.
תריצי את זה פעם אחת, תתחברי ידנית עם 2FA, ואז הסשן יישמר.

הרצה: python scraper/save_session.py
"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SEHEL_URL = "https://crm.sehel.co.il"
SESSION_DIR = Path(__file__).resolve().parent / "session_data"


def main():
    SESSION_DIR.mkdir(exist_ok=True)

    print("=" * 50)
    print("  שמירת Session — התחברות ידנית")
    print("=" * 50)
    print()
    print("1. ייפתח דפדפן")
    print("2. התחברי עם שם משתמש + סיסמא + קוד 2FA")
    print("3. אחרי שנכנסת למערכת — חזרי לטרמינל ולחצי Enter")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )

        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(SEHEL_URL)

        input("\n✋ אחרי שהתחברת בהצלחה — לחצי Enter כאן...")

        # שומר cookies
        cookies = browser.cookies()
        print(f"\n✓ נשמרו {len(cookies)} cookies")
        print(f"✓ Session נשמר בתיקייה: {SESSION_DIR}")
        print("\nמעכשיו הסקריפט האוטומטי ירוץ בלי 2FA!")

        browser.close()


if __name__ == "__main__":
    main()
