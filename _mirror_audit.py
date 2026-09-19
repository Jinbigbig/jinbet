# -*- coding: utf-8 -*-
"""results_history 镜像/重复 全量审计（只读）。

对每个 matchId 组，判定：
  - 组大小
  - 是否跨日（真孪生） / 同日（别名或同向重复）
  - 各组员与 results_data 锚点的方向关系（同向 / 反向 / 无锚）
"""
import json
import glob
import os
import collections

ROOT = os.path.dirname(os.path.abspath(__file__))
rd = json.load(open(os.path.join(ROOT, 'results_data.json'), encoding='utf-8'))

# 锚点：matchId -> (home, away)
anchor = {}
for k, v in rd.items():
    if isinstance(v, dict) and v.get('matchId'):
        if v.get('home') and v.get('away'):
            anchor.setdefault(str(v['matchId']), (v['home'], v['away']))
# 反向键集合：(date, away, home)
rev_keys = set()
for k, v in rd.items():
    p = k.split('_', 2)
    if len(p) == 3:
        rev_keys.add(f'{p[0]}_{p[2]}_{p[1]}')

groups = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json'))):
    date = os.path.basename(f)[:-5]
    for k, v in json.load(open(f, encoding='utf-8')).items():
        if isinstance(v, dict):
            groups[str(v.get('matchId'))].append((date, k, v))

stat = collections.Counter()
detail = collections.defaultdict(list)
for mid, items in groups.items():
    n = len(items)
    dates = set(d for d, _, _ in items)
    kind = '同日' if len(dates) == 1 else '跨日'
    a = anchor.get(mid)
    rel = []
    for d, k, v in items:
        if a and (v.get('home'), v.get('away')) == a:
            rel.append('同向')
        elif a and (v.get('home'), v.get('away')) == (a[1], a[0]):
            rel.append('反向')
        elif k in rd:
            rel.append('键同向')
        elif k in rev_keys:
            rel.append('键反向')
        else:
            rel.append('无锚')
    if n == 1:
        stat[f'单条/{rel[0]}'] += 1
        if rel[0] in ('反向', '键反向', '无锚'):
            detail[f'单条/{rel[0]}'].append((mid, items[0]))
    else:
        stat[f'{kind}/{n}条/{",".join(sorted(set(rel)))}'] += 1
        detail[f'{kind}/{n}条/{",".join(sorted(set(rel)))}'].append((mid, items))

print('=== 组结构 × 锚点关系 ===')
for k in sorted(stat, key=lambda x: -stat[x]):
    print(f'  {k:<34} {stat[k]}')
print()
print('总记录', sum(len(v) for v in groups.values()), '| 唯一 matchId', len(groups))

for key in sorted(detail):
    if key.startswith('单条/') and key.endswith('无锚'):
        print(f'\n--- {key} 前 10 例 ---')
        for mid, it in detail[key][:10]:
            print('   ', mid, it[0], it[1][:46], it[2].get('home'), 'vs', it[2].get('away'), it[2].get('fullScore'))
    elif key.startswith('单条/'):
        print(f'\n--- {key} 前 12 例 ---')
        for mid, it in detail[key][:12]:
            print('   ', mid, it[0], it[2].get('home'), 'vs', it[2].get('away'), it[2].get('fullScore'), '| 锚', anchor.get(mid))
    elif key.startswith('跨日'):
        print(f'\n--- {key} 前 4 例 ---')
        for mid, its in detail[key][:4]:
            print('   id', mid, '锚', anchor.get(mid))
            for d, k, v in sorted(its):
                print('      ', d, v.get('home'), 'vs', v.get('away'), v.get('fullScore'))
