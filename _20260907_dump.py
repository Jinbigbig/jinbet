import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.load(open(r'odds_data.json', encoding='utf-8'))
data = d.get('data', {})
hits = []
for k, v in data.items():
    if isinstance(v, dict) and v.get('date_key', '').startswith('2026-09-07'):
        hits.append((k, v))
print('09-07 matches:', len(hits))
for k, v in sorted(hits, key=lambda x: int(x[1].get('matchNo') or 0)):
    print('=' * 60)
    print(k, '| 编号:', v.get('matchNumStr'), '| 联赛:', v.get('league'))
    print('胜平负:', v.get('胜'), v.get('平'), v.get('负'))
    print('让球:', v.get('让球'))
    print('比分:', json.dumps(v.get('比分', {}), ensure_ascii=False)[:400])
    print('总进球:', v.get('总进球'))
    print('半全场:', v.get('半全场'))
