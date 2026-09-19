import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.load(open(r'odds_data.json', encoding='utf-8'))
print('updated:', d.get('updated'))
print('count:', d.get('count'))
data = d.get('data', {})
if isinstance(data, dict):
    for k, v in data.items():
        if '2026-09-07' in str(k):
            print('KEY:', k)
            print(json.dumps(v, ensure_ascii=False, indent=1)[:3000])
else:
    for item in data:
        s = json.dumps(item, ensure_ascii=False)
        if '2026-09-07' in s or '09-07' in s:
            print(item)
