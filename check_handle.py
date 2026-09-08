import sys
sys.stdout.reconfigure(encoding='utf-8')
p = r'c:\Users\STD2568\Desktop\oren-cohen-bot\app\whatsapp.py'
content = open(p, encoding='utf-8').read()
idx = content.find('async def _handle_message')
print(repr(content[idx:idx+500]))
