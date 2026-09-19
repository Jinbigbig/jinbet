import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.load(open(r'odds_data.json', encoding='utf-8'))
data = d.get('data', {})
targets = ['马尔默 vs 索尔纳', '卡尔马 vs 佐加顿斯', '利雅新月 vs 新未来SC', '乌迪内斯 vs 拉齐奥', '埃尔切 vs 皇家社会']
for t in targets:
    v = data.get(t)
    if v:
        print('FOUND', t, '| date_key:', v.get('date_key'), '| 编号:', v.get('matchNumStr'))
    else:
        # fuzzy search
        for k, vv in data.items():
            if t.split(' vs ')[0] in k and t.split(' vs ')[1] in k:
                print('FUZZY', k, '| date_key:', vv.get('date_key'), '| 编号:', vv.get('matchNumStr'))
