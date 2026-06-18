import json, sys
sys.stdout.reconfigure(encoding='utf-8')
data = json.loads(open('feedback_dump.json', encoding='utf-8').read())
trainings = [d for d in data if d.get('rating') == 'training' and d.get('transcript')]
for i, t in enumerate(trainings[15:]):
    msgs = t.get('transcript', [])
    print(f'\n====== Session {i+16} ======')
    for msg in msgs:
        role = msg.get('role','?')
        content = msg.get('content','')[:200]
        print(f'  {role}: {content}')
