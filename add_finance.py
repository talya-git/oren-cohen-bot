import sys
sys.stdout.reconfigure(encoding='utf-8')
p = r'c:\Users\STD2568\Desktop\oren-cohen-bot\static\calendar.html'
c = open(p, encoding='utf-8').read()

# Add finance to DEPT_LABELS
c = c.replace(
    "const DEPT_LABELS = { projects: '\u05de\u05d7\u05dc\u05e7\u05ea \u05e4\u05e8\u05d5\u05d9\u05e7\u05d8\u05d9\u05dd', yad2: '\u05de\u05d7\u05dc\u05e7\u05ea \u05d9\u05d3 2', az: '\u05de\u05d7\u05dc\u05e7\u05ea A-Z' };",
    "const DEPT_LABELS = { projects: '\u05de\u05d7\u05dc\u05e7\u05ea \u05e4\u05e8\u05d5\u05d9\u05e7\u05d8\u05d9\u05dd', yad2: '\u05de\u05d7\u05dc\u05e7\u05ea \u05d9\u05d3 2', az: '\u05de\u05d7\u05dc\u05e7\u05ea A-Z', finance: '\u05de\u05d7\u05dc\u05e7\u05ea \u05db\u05e1\u05e4\u05d9\u05dd' };"
)

# Add finance button - find exact surrounding
old_btn = ">A-Z</button>      </div>"
new_btn = ">A-Z</button>\n        <button onclick=\"chooseDept('finance')\" style=\"padding:16px;border-radius:12px;border:2px solid #e2e8f0;background:#f8fafc;font-size:16px;font-weight:600;color:#1e293b;cursor:pointer;transition:all 0.15s\" onmouseover=\"this.style.borderColor='#6366f1';this.style.background='#eef2ff'\" onmouseout=\"this.style.borderColor='#e2e8f0';this.style.background='#f8fafc'\">\u05db\u05e1\u05e4\u05d9\u05dd</button>      </div>"

if old_btn in c:
    c = c.replace(old_btn, new_btn)
    print('finance button added')
else:
    print('NOT FOUND')

open(p, 'w', encoding='utf-8').write(c)
print('done')
