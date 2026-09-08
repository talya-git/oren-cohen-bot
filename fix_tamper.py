import sys
sys.stdout.reconfigure(encoding='utf-8')
p = r'c:\Users\STD2568\Desktop\oren-cohen-bot\tampermonkey_script.js'
c = open(p, encoding='utf-8').read()

# Fix duplicate netanel and add finance dept label
old = """        { label: '\u05e0\u05ea\u05e0\u05d0\u05dc',  email: 'netanel@orencohengroup.com' },
        { label: '\u05e0\u05e2\u05de\u05d9',   email: 'NaomiS@orencohengroup.com' },
        { label: '\u05e0\u05ea\u05e0\u05d0\u05dc',  email: 'netanel@orencohengroup.com' },
    ];"""

new = """        { label: '\u05e0\u05ea\u05e0\u05d0\u05dc',  email: 'netanel@orencohengroup.com' },
        { label: '\u05e0\u05e2\u05de\u05d9',   email: 'NaomiS@orencohengroup.com' },
    ];"""

if old in c:
    c = c.replace(old, new)
    print('duplicate removed')
else:
    print('duplicate not found')

open(p, 'w', encoding='utf-8').write(c)
print('done')
