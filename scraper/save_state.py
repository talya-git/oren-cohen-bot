"""שמירת session עם storage_state - גישה חדשה."""

from playwright.sync_api import sync_playwright
from pathlib import Path
import json

SD = Path(__file__).resolve().parent / "session_data"
SD.mkdir(exist_ok=True)

p = sync_playwright().start()
b = p.chromium.launch(headless=False)
ctx = b.new_context()
page = ctx.new_page()
page.goto("https://crm.sehel.co.il")

print("=" * 50)
print("1. התחברי עם שם משתמש + סיסמא + קוד 2FA")
print("2. חכי שתראי את הדשבורד (לוח בקרה)")
print("3. רק אז חזרי לכאן ולחצי Enter")
print("=" * 50)

input("\nEnter אחרי שאת בפנים: ")

print("URL:", page.url)
state = ctx.storage_state()
json.dump(state, open(str(SD / "state.json"), "w"))
print(f"Cookies: {len(state['cookies'])}")
print(f"Origins: {len(state['origins'])}")
print("נשמר!")

input("Enter לסגור: ")
b.close()
p.stop()
