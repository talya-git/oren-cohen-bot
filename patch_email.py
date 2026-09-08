import sys
sys.stdout.reconfigure(encoding='utf-8')

p = r'c:\Users\STD2568\Desktop\oren-cohen-bot\app\email_api.py'
content = open(p, encoding='utf-8').read()

idx = content.find('def _build_greeting')
end = content.find('\n\n\n@router', idx)

new_func = (
    'def _build_greeting(name: str | None) -> str:\n'
    '    is_hebrew = name and any(\'\\u05d0\' <= c <= \'\\u05ea\' for c in name)\n'
    '    if is_hebrew or not name:\n'
    '        greeting = f"\u05d4\u05d9\u05d9{\' \' + name if name else \'\'},\\n\\n"\n'
    '        greeting += (\n'
    '            "\u05db\u05d0\u05df \u05d3\u05e0\u05d9\u05d0\u05dc \u05de\u05d0\u05d5\u05e8\u05df \u05db\u05d4\u05df \u05d2\u05e8\u05d5\u05e4 \u05d1\u05d9\u05e8\u05d5\u05e9\u05dc\u05d9\u05dd.\\n"\n'
    '            "\u05d0\u05e0\u05d9 \u05e4\u05d5\u05e0\u05d4 \u05d0\u05dc\u05d9\u05da \u05d1\u05d4\u05de\u05e9\u05da \u05dc\u05e4\u05e0\u05d9\u05d9\u05ea\u05da \u05dc\u05de\u05e9\u05e8\u05d3\u05e0\u05d5 \u05d1\u05e2\u05d1\u05e8.\\n\\n"\n'
    '            "\u05d1\u05d9\u05de\u05d9\u05dd \u05d0\u05dc\u05d5 \u05d0\u05e0\u05d7\u05e0\u05d5 \u05de\u05e8\u05db\u05d6\u05d9\u05dd \u05e2\u05d1\u05d5\u05e8 \u05dc\u05e7\u05d5\u05d7\u05d5\u05ea\u05d9\u05e0\u05d5 \u05de\u05e1\u05e4\u05e8 \u05d4\u05d6\u05d3\u05de\u05e0\u05d5\u05d9\u05d5\u05ea \u05e0\u05d3\u05dc\\"\\u05df \u05de\u05d9\u05d5\u05d7\u05d3\u05d5\u05ea \u05d1\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8\u05d9\u05dd \u05e2\u05ea\u05d9\u05d3\u05d9\u05d9\u05dd \u05d1\u05d9\u05e8\u05d5\u05e9\u05dc\u05d9\u05dd.\\n\\n"\n'
    '            "\u05d4\u05d0\u05dd \u05d4\u05e0\u05d5\u05e9\u05d0 \u05e2\u05d3\u05d9\u05d9\u05df \u05e8\u05dc\u05d5\u05d5\u05e0\u05d8\u05d9 \u05e2\u05d1\u05d5\u05e8\u05da?\\n\\n"\n'
    '            "\u05d1\u05d1\u05e8\u05db\u05d4,\\n\u05d3\u05e0\u05d9\u05d0\u05dc\\n\u05d0\u05d5\u05e8\u05df \u05db\u05d4\u05df \u05d2\u05e8\u05d5\u05e4"\n'
    '        )\n'
    '    else:\n'
    '        greeting = f"Hi {name},\\n\\n"\n'
    '        greeting += (\n'
    '            "How are you? This is Daniel from Oren Cohen Group.\\n\\n"\n'
    '            "Following your previous inquiry with our office, I wanted to let you know that we\'re about to launch several unique new projects in some of Jerusalem\'s most sought-after locations.\\n\\n"\n'
    '            "Since you were looking in the past, I thought it would be right to reach out to you first, before we introduce them to the wider market.\\n\\n"\n'
    '            "Would this be of interest to you?\\n\\n"\n'
    '            "Best regards,\\nDaniel\\nOren Cohen Group"\n'
    '        )\n'
    '    return greeting'
)

content = content[:idx] + new_func + content[end:]

# Fix subject - remove the "— אורן כהן גרופ" part and shorten
content = content.replace(
    '\u05d4\u05d6\u05d3\u05de\u05e0\u05d5\u05d9\u05d5\u05ea \u05e0\u05d3\u05dc\u05df \u05d1\u05d9\u05e8\u05d5\u05e9\u05dc\u05d9\u05dd',
    '\u05d4\u05d6\u05d3\u05de\u05e0\u05d5\u05d9\u05d5\u05ea \u05e0\u05d3\u05dc\u05df'
)
content = content.replace(
    'Real Estate Opportunities in Jerusalem',
    'Real Estate Opportunities in Jerusalem'
)

open(p, 'w', encoding='utf-8').write(content)

log = open(r'c:\Users\STD2568\Desktop\oren-cohen-bot\patch_log.txt', 'w', encoding='utf-8')
log.write('OK\n')
log.write(content[idx:idx+300])
log.close()
