"""
סקריפט חד-פעמי — שולח callSummary לשכל עבור כל השיחות הישנות שיש להן transcript.
הרצה מתיקיית הפרויקט: python scripts/backfill_call_summaries.py
"""
import os
import sys
import time
from pathlib import Path

# טעינת משתני סביבה מ-.env
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database as db
from app import sehel


def main():
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT phone, client_name, transcript
        FROM reengagement_sent
        WHERE transcript IS NOT NULL AND transcript != ''
    """)
    rows = db._fetchall(cur)
    conn.close()

    dry_run = not (sehel.PROJECT_ID or sehel.WEBHOOK_URL)
    if dry_run:
        print("⚠️  DRY RUN — אין SEHEL_PROJECT_ID, לא שולח בפועל")

    print(f"נמצאו {len(rows)} שיחות עם transcript")

    for i, row in enumerate(rows, 1):
        phone = row["phone"]
        name = row.get("client_name") or ""
        transcript = row.get("transcript") or ""
        summary = f"בוט וואטסאפ — שיחה עם {name}:\n{transcript[:1800]}"
        try:
            result = sehel.log_call_summary(phone, summary, dry_run=dry_run)
            print(f"[{i}/{len(rows)}] ✅ {phone} | {name} → {result}")
        except Exception as e:
            print(f"[{i}/{len(rows)}] ❌ {phone} | {name} → {e}")
        time.sleep(0.5)

    print("✅ סיום")


if __name__ == "__main__":
    main()
