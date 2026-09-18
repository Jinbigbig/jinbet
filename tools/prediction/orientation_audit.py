# -*- coding: utf-8 -*-
"""全库方向审计：每条 results_history 记录 vs 官方 API（只读，结果缓存到本地）。

输出：按（月份 × 组类型）统计 同向/反向/无官方。
"""
import json
import glob
import os
import re
import time
import datetime
import urllib.request
import collections

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, '_official_results_cache.json')
H = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.sporttery.cn/jc/zqsgkj/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Encoding': 'identity',
    'Origin': 'https://www.sporttery.cn',
}


def fetch_all():
    out = []
    s = datetime.date(2025, 12, 25)
    while s <= datetime.date(2026, 9, 10):
        e = s + datetime.timedelta(days=9)
        for p in range(1, 12):
            url = (f'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
                   f'?matchBeginDate={s.isoformat()}&matchEndDate={e.isoformat()}&leagueId='
                   f'&pageSize=100&pageNo={p}&isFix=0&matchPage=1&pcOrWap=1')
            try:
                d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40).read().decode('utf-8'))
            except Exception as ex:
                print('  err', s, e, p, ex)
                break
            ms = (d.get('value') or {}).get('matchResult') or []
            out += ms
            if len(ms) < 100:
                break
            time.sleep(0.1)
        s = e + datetime.timedelta(days=1)
    return out


if os.path.exists(CACHE):
    off = json.load(open(CACHE, encoding='utf-8'))
    print(f'官方缓存 {len(off)} 场')
else:
    off = fetch_all()
    json.dump(off, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'官方抓取 {len(off)} 场 → 缓存 {CACHE}')

idx = collections.defaultdict(list)
for m in off:
    h, a = m.get('homeTeam'), m.get('awayTeam')
    if h and a:
        idx[(m.get('matchDate'), frozenset((h, a)))].append(m)


def same(x, y):
    if not x or not y:
        return False
    cx = re.sub(r'[\s\-（）()]', '', str(x))
    cy = re.sub(r'[\s\-（）()]', '', str(y))
    return cx == cy or (len(cx) >= 2 and len(cy) >= 2 and (cx.startswith(cy) or cy.startswith(cx)))


def verdict(date, h, a):
    for delta in (0, 1, -1, 2, -2):
        try:
            dd = (datetime.date.fromisoformat(date) + datetime.timedelta(days=delta)).isoformat()
        except Exception:
            continue
        for m in idx.get((dd, frozenset((h, a))), []):
            if same(m.get('homeTeam'), h) and same(m.get('awayTeam'), a):
                return 'fwd'
            if same(m.get('homeTeam'), a) and same(m.get('awayTeam'), h):
                return 'rev'
    return 'none'


groups = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json'))):
    date = os.path.basename(f)[:-5]
    for k, v in json.load(open(f, encoding='utf-8')).items():
        if isinstance(v, dict):
            groups[str(v.get('matchId'))].append((date, k, v))

stat = collections.defaultdict(collections.Counter)
for mid, items in groups.items():
    dates = sorted(set(x[0] for x in items))
    if len(items) == 1:
        kind = '单条'
    elif len(dates) == 1:
        kind = '同日重复'
    else:
        kind = '孪生-早' 
    for i, (d, k, v) in enumerate(sorted(items, key=lambda x: x[0])):
        if kind == '孪生-早' and i > 0:
            kk = '孪生-晚'
        else:
            kk = kind
        stat[d[:7]][kk + '/' + verdict(d, v.get('home'), v.get('away'))] += 1

print()
print('=== 月份 × 类型 × 官方方向 ===')
tot = collections.Counter()
for mon in sorted(stat):
    parts = ' '.join(f'{k}={v}' for k, v in sorted(stat[mon].items()))
    print(f'  {mon}: {parts}')
    for k, v in stat[mon].items():
        tot[k.split('/')[0] + '/' + k.split('/')[1]] += v
print()
print('=== 汇总 ===')
for k in sorted(tot):
    print(f'  {k}: {tot[k]}')

print()
print('=== 各类别反向率 ===')
for kind in ['单条', '同日重复', '孪生-早', '孪生-晚']:
    f = sum(v for k, v in tot.items() if k.startswith(kind + '/fwd'))
    r = sum(v for k, v in tot.items() if k.startswith(kind + '/rev'))
    n = sum(v for k, v in tot.items() if k.startswith(kind + '/'))
    print(f'  {kind:<8} 同向 {f:<5} 反向 {r:<5} 无官方 {n - f - r:<5} → 反向率 {r / max(f + r, 1):.1%}')
