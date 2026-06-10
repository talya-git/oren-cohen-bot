"""
סקריפט שרץ ברקע ומעדכן את המאגר כל 30 דקות עם מונה.

הרצה: python scraper/run_loop.py
"""

import time
import subprocess
import sys
from datetime import datetime
from pathlib import Path

INTERVAL_SECONDS = 30 * 60  # 30 דקות
SCRAPER_PATH = Path(__file__).resolve().parent / "scrape_sehel.py"


def run_scraper():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] מריץ עדכון...")
    try:
        result = subprocess.run(
            [sys.executable, str(SCRAPER_PATH)],
            cwd=str(SCRAPER_PATH.parent.parent),
            timeout=300,
        )
        if result.returncode == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ עדכון הצליח")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ נכשל")
    except subprocess.TimeoutExpired:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ timeout")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ שגיאה: {e}")


def countdown(seconds):
    """מונה שיורד כל שניה."""
    while seconds > 0:
        mins = seconds // 60
        secs = seconds % 60
        print(f"\r⏳ עדכון הבא בעוד: {mins:02d}:{secs:02d}", end="", flush=True)
        time.sleep(1)
        seconds -= 1
    print("\r" + " " * 40 + "\r", end="")


if __name__ == "__main__":
    print("=" * 40)
    print("  Sehel Auto-Update — כל 30 דקות")
    print("  לסגירה: Ctrl+C")
    print("=" * 40)

    while True:
        run_scraper()
        countdown(INTERVAL_SECONDS)
