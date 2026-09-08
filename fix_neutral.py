# -*- coding: utf-8 -*-
files = ['app/engine.py', 'app/whatsapp.py', 'app/prompts/prompt_he.md', 'app/prompts/prompt_en.md']

for fname in files:
    c = open(fname, 'r', encoding='utf-8').read()
    original = c
    c = c.replace('נשמח שתשמור אותנו בזיכרון שלך', 'נשמח להישמר בזיכרון שלך')
    c = c.replace("We'd love to stay in your memory", "We'd love to be remembered by you")
    if c != original:
        open(fname, 'w', encoding='utf-8').write(c)
        print(f'{fname}: updated')
    else:
        print(f'{fname}: no change')
