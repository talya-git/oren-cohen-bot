"""סקריפט חד-פעמי — שולח סיכום שיחה לשכל עבור 12 לידים של ינון מ-11.8.2026."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

# אם DATABASE_URL לא ב-.env — קח מהסביבה (Render)
if not os.getenv("DATABASE_URL"):
    print("ERROR: DATABASE_URL לא מוגדר")
    sys.exit(1)

from app import sehel, database as db

PHONES = [
    "+972503404210",  # אלון
    "+972508825050",  # שמואל
    "+972522830388",  # אבי
    "+972528119323",  # אפרת כהן
    "+972542835573",  # שירן שרמן
    "+972523677070",  # תומר אוהב ציון
    "+972507669526",  # אדם בן מיכאל
    "+972523776777",  # יגאל
    "+972587891001",  # אלעד הדרי
    "+972522860799",  # לורן בובליל
    "+972548161705",  # Shalom Cohen
    "+972547587673",  # דוד ליפן
]

for phone in PHONES:
    record = db.get_reengagement_record(phone)
    if not record:
        print(f"[SKIP] {phone} — לא נמצא ב-DB")
        continue

    transcript = record.get("transcript") or ""
    name = record.get("client_name") or ""
    replied = record.get("replied") or False

    if transcript:
        summary = f"בוט וואטסאפ — ינון — {name}:\n{transcript}"
    else:
        summary = f"בוט וואטסאפ — ינון — {name}: לא ענה"

    try:
        result = sehel.log_call_summary(phone, summary)
        print(f"[OK] {phone} ({name}) replied={replied} → {result}")
    except Exception as e:
        print(f"[ERROR] {phone} ({name}) → {e}")
