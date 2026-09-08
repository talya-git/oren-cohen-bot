import sys, os
sys.stdout.reconfigure(encoding='utf-8')

p = r'c:\Users\STD2568\Desktop\oren-cohen-bot\app\whatsapp.py'
content = open(p, encoding='utf-8').read()

# Remove the broken _handle_message stub and the broken debounce block
# Replace with clean version

old = '''async def _handle_message(phone: str, text: str, _db) -> None:
    """מעבד הודעה (או מספר הודעות מאוחדות) מלקוח."""
    from .engine import Conversation
    if phone in _wa_done or _db.is_conversation_done(phone):


@router.get("/webhook")'''

new = '''@router.get("/webhook")'''

if old in content:
    content = content.replace(old, new)
    print('removed broken _handle_message stub')
else:
    print('stub not found, checking...')
    idx = content.find('async def _handle_message')
    print(f'_handle_message at: {idx}')

# Also fix the debounce block - replace the broken return with proper indented code
old2 = '''    task = asyncio.create_task(_process_after_delay(phone))
    _wa_debounce_tasks[phone] = task
    return {"status": "queued"}
        # בדוק אם זו תשובה שלילית אחרי סיום השיחה'''

new2 = '''    task = asyncio.create_task(_process_after_delay(phone))
    _wa_debounce_tasks[phone] = task
    return {"status": "queued"}


async def _handle_message(phone: str, text: str, _db) -> None:
    """מעבד הודעה (או מספר הודעות מאוחדות) מלקוח."""
    from .engine import Conversation
    if phone in _wa_done or _db.is_conversation_done(phone):
        # בדוק אם זו תשובה שלילית אחרי סיום השיחה'''

if old2 in content:
    content = content.replace(old2, new2)
    print('fixed debounce block')
else:
    print('debounce block not found')
    idx2 = content.find('return {"status": "queued"}')
    print(f'queued return at: {idx2}')
    print(repr(content[idx2:idx2+200]))

open(p, 'w', encoding='utf-8').write(content)
print('done')
