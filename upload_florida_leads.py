"""
מייבא florida_leads_fixed.xlsx לשרת דרך API
הרצה: python upload_florida_leads.py
"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
import openpyxl, requests

FILE = r'c:\Users\STD2568\Downloads\florida_leads_fixed.xlsx'
SERVER = 'https://oren-cohen-bot.onrender.com'

wb = openpyxl.load_workbook(FILE)
ws = wb.active

leads = []
for row in ws.iter_rows(min_row=2, values_only=True):
    if not row[0] and not row[1]:
        continue
    leads.append({
        'name':             str(row[0] or '').strip(),
        'phone1':           str(row[1] or '').strip().lstrip("'"),
        'phone2':           str(row[2] or '').strip().lstrip("'") if row[2] else '',
        'email':            str(row[3] or '').strip() if row[3] else '',
        'project':          str(row[4] or '').strip() if row[4] else '',
        'agent':            str(row[5] or '').strip() if row[5] else '',
        'created_date':     str(row[6] or '').strip() if row[6] else '',
        'area_code':        str(row[8] or '').strip() if len(row) > 8 and row[8] else '',
        'florida_location': str(row[9] or '').strip() if len(row) > 9 and row[9] else '',
    })

print(f"שולח {len(leads)} לקוחות...")
resp = requests.post(
    f'{SERVER}/api/florida/import-leads',
    json={'leads': leads, 'secret': 'florida2025import'},
    timeout=60
)
print(f"סטטוס: {resp.status_code}")
print(resp.json())
