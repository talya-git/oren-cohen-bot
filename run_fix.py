p = r'c:\Users\STD2568\Desktop\oren-cohen-bot\build_conv.py'
open(p, 'w', encoding='utf-8').write(r"""
import os
p = r'c:\Users\STD2568\Desktop\oren-cohen-bot\static\conversations.html'
html = open(p, encoding='utf-8').read()
# Find the broken part - code outside script tag
marker = '</script>\nlet openPhone'
if marker in html:
    # wrap the orphaned code back into a script tag
    html = html.replace(marker, '</script>\n<script>\nconst API = \'\';\nlet allData = [];\nlet openPhone')
    open(p, 'w', encoding='utf-8').write(html)
    log = open(r'c:\Users\STD2568\Desktop\oren-cohen-bot\conv_fix.txt', 'w')
    log.write('FIXED\n')
    log.close()
else:
    log = open(r'c:\Users\STD2568\Desktop\oren-cohen-bot\conv_fix.txt', 'w')
    log.write('MARKER NOT FOUND\n')
    # check what's around the issue
    idx = html.find('let openPhone')
    log.write(f'openPhone at: {idx}\n')
    log.write(repr(html[max(0,idx-50):idx+50]))
    log.close()
""")
