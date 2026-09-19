# -*- coding: utf-8 -*-
"""全库方向体检：用 odds_history/*/schedule（官方赔率源，方向权威）当锚，扫描 2026 全年"""
import json, os, glob
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
res = json.load(open(os.path.join(ROOT, 'results_data.json'), 'r', encoding='utf-8'))

anchor = {}
nfiles = 0
for fp in sorted(glob.glob(os.path.join(ROOT, 'odds_history', '*.json'))):
    base = os.path.basename(fp).replace('.json', '')
    if base == 'index':
        continue
    try:
        o = json.load(open(fp, 'r', encoding='utf-8'))
    except Exception:
        continue
    if not isinstance(o, dict) or 'schedule' not in o:
        continue
    nfiles += 1
    for g in o['schedule']:
        d = o.get('date') or base
        h, a = g.get('home', ''), g.get('away', '')
        if h and a:
            anchor[(d, frozenset((h, a)))] = (h, a)

print(f'锚点来源: {nfiles} 个赔率归档日；锚点场次 {len(anchor)}')

same = rev = 0
by_month = Counter(); by_month_rev = Counter()
rev_keys = []
for k, v in res.items():
    p = k.split('_', 2)
    if len(p) != 3:
        continue
    a = anchor.get((p[0], frozenset(p[1:])))
    if not a:
        continue
    lh, la = v.get('home', ''), v.get('away', '')
    m = p[0][:7]
    by_month[m] += 1
    if (lh, la) == a:
        same += 1
    else:
        rev += 1
        by_month_rev[m] += 1
        if len(rev_keys) < 6:
            rev_keys.append((k, lh, la, a, str(v.get('score') or v.get('fullScore') or '')))

tot = same + rev
print(f'可判定: {tot}')
print(f'  与官方赔率源方向【一致】: {same} ({same/max(tot,1)*100:.2f}%)')
print(f'  与官方赔率源方向【颠倒】: {rev} ({rev/max(tot,1)*100:.2f}%)')
print()
print('按月份：')
for m in sorted(by_month):
    print(f'  {m}  可判定 {by_month[m]:<5} 颠倒 {by_month_rev[m]:<5} ({by_month_rev[m]/by_month[m]*100:5.1f}%)')

print()
print('颠倒样例：')
for x in rev_keys:
    print(f'  results key = {x[0]}  (home={x[1]}, away={x[2]}, score={x[4]})')
    print(f'      官方 schedule home={x[3][0]}, away={x[3][1]}')
