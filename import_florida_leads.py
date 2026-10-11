"""
מייבא את leads_export.xlsx לטבלת florida_leads ב-DB
הרצה: python import_florida_leads.py
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import openpyxl
from dotenv import load_dotenv
load_dotenv()

import psycopg2
DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# יצירת טבלה
cur.execute("""
    CREATE TABLE IF NOT EXISTS florida_leads (
        id SERIAL PRIMARY KEY,
        name TEXT,
        phone1 TEXT,
        phone2 TEXT,
        email TEXT,
        project TEXT,
        agent TEXT,
        created_date TEXT,
        status TEXT,
        area_code TEXT,
        florida_location TEXT,
        sent BOOLEAN DEFAULT FALSE,
        sent_at TIMESTAMPTZ,
        registered BOOLEAN DEFAULT FALSE
    )
""")
conn.commit()

# בדיקה אם כבר יובא
cur.execute("SELECT COUNT(*) FROM florida_leads")
count = cur.fetchone()[0]
if count > 0:
    print(f"כבר קיימים {count} רשומות. מדלג.")
    conn.close()
    sys.exit(0)

wb = openpyxl.load_workbook(r'c:\Users\STD2568\Downloads\florida_leads_fixed.xlsx')
ws = wb.active

imported = 0
for row in ws.iter_rows(min_row=2, values_only=True):
    if not row[0] and not row[1]:
        continue
    name     = str(row[0] or '').strip()
    phone1   = str(row[1] or '').strip().lstrip("'")
    phone2   = str(row[2] or '').strip().lstrip("'")
    email    = str(row[3] or '').strip()
    project  = str(row[4] or '').strip()
    agent    = str(row[5] or '').strip()
    created  = str(row[6] or '').strip()
    status   = str(row[7] or '').strip()
    prefix   = str(row[8] or '').strip() if len(row) > 8 else ''
    location = str(row[9] or '').strip() if len(row) > 9 else ''
    cur.execute("""
        INSERT INTO florida_leads (name,phone1,phone2,email,project,agent,created_date,status,area_code,florida_location)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        name or None, phone1 or None,
        phone2 if phone2 not in ('None','') else None,
        email if email not in ('None','') else None,
        project or None, agent or None, created or None,
        status if status not in ('None','') else None,
        prefix or None, location or None,
    ))
    imported += 1

conn.commit()
conn.close()
print(f"\n✅ יובאו {imported} לקוחות פלורידה ל-DB")
