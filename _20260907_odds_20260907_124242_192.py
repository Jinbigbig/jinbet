import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.load(open(r'odds_data.json', encoding='utf-8'))
data = d.get('data')
print('data type:', type(data))
if isinstance(data, list):
    print('len:', len(data))
    print('first item keys:', list(data[0].keys()) if data and isinstance(data[0], dict) else data[0])
    # find 09-07
    hits = []
    for it in data:
        s = json.dumps(it, ensure_ascii=False)
        if '2026-09-07' in s:
            hits.append(it)
    print('hits:', len(hits))
    for it in hits[:12]:
        print(json.dumps(it, ensure_ascii=False))
elif isinstance(data, dict):
    print('keys:', list(data.keys())[:20])
    for k, v in list(data.items())[:3]:
        print('K', k)
        print(json.dumps(v, ensure_ascii=False)[:800])
