import sys
sys.stdout.reconfigure(encoding='utf-8')
p = r'c:\Users\STD2568\Desktop\oren-cohen-bot\tampermonkey_script.js'
c = open(p, encoding='utf-8').read()

# Find isChecked line and fix it
old = "            const isChecked = !wl_unchecked.has(phone);"
new = "            const isChecked = !wl_unchecked.has(phone) && !alreadySent;"

if old in c:
    c = c.replace(old, new)
    print('isChecked fixed')
else:
    print('NOT FOUND')
    idx = c.find('isChecked')
    print(repr(c[idx:idx+100]))

open(p, 'w', encoding='utf-8').write(c)
print('done')
