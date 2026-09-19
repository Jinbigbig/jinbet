# -*- coding: utf-8 -*-
"""用体彩官方赛果 API 核实 results_history 中「方向存疑」的记录（只读，不改文件）。

目标集合：
  1) 单条但 (date, away, home) 键存在于 results_data 的记录（方向冲突）
  2) 同日多条的组（别名/重复）
官方 API 用竞彩 matchId，可直接 join。
"""
import json
import glob
import os
import time
import urllib.request
import collections

ROOT = os.path.dirname(os.path.abspath(__file__))
H = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.sporttery.cn/jc/zqsgkj/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Encoding': 'identity',
    'Origin': 'https://www.sporttery.cn',
}


def q(a, b):
    out = []
    for p in range(1, 8):
        url = (f'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
               f'?matchBeginDate={a}&matchEndDate={b}&leagueId=&pageSize=100&pageNo={p}'
               f'&isFix=0&matchPage=1&pcOrWap=1')
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40).read().decode('utf-8'))
        except Exception as e:
            print('  API err', a, b, e)
            break
        ms = d.get('value', {}).get('matchResult', []) or []
        out += ms
        if len(ms) < 100:
            break
        time.sleep(0.2)
    return out


rd = json.load(open(os.path.join(ROOT, 'results_data.json'), encoding='utf-8'))
rev_keys = set()
for k in rd:
    p = k.split('_', 2)
    if len(p) == 3:
        rev_keys.add(f'{p[0]}_{p[2]}_{p[1]}')

groups = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json'))):
    date = os.path.basename(f)[:-5]
    for k, v in json.load(open(f, encoding='utf-8')).items():
        if isinstance(v, dict):
            groups[str(v.get('matchId'))].append((date, k, v))

suspect = {}   # mid -> (date, key, rec, reason)
for mid, items in groups.items():
    if len(items) == 1:
        d, k, v = items[0]
        if k in rev_keys:
            suspect[mid] = (d, k, v, '单条反向键')
    else:
        dates = set(x[0] for x in items)
        if len(dates) == 1:
            for d, k, v in items:
                suspect.setdefault(mid, (d, k, v, '同日重复'))
            suspect[mid] = (items[0][0], items[0][1], items[0][2], f'同日{len(items)}条')

print(f'存疑 matchId {len(suspect)} 个')
dates = sorted(set(v[0] for v in suspect.values()))
print('涉及日期', dates[0], '~', dates[-1], f'共 {len(dates)} 天')

# 逐段查询官方
official = {}
i = 0
while i < len(dates):
    a = dates[i]
    j = i
    while j + 1 < len(dates) and j - i < 6:
        j += 1
    b = dates[j]
    ms = q(a, b)
    for m in ms:
        official[str(m.get('matchId'))] = m
    print(f'  查询 {a}~{b}: 官方 {len(ms)} 场（累计索引 {len(official)}）')
    i = j + 1

print()
print('=== 逐场判定 ===')
res = collections.Counter()
rows = []
for mid, (d, k, v, why) in sorted(suspect.items()):
    m = official.get(str(mid))
    if not m:
        res['官方无此id'] += 1
        rows.append((mid, d, v, why, '官方无此id', None))
        continue
    oh, oa = m.get('homeTeam'), m.get('awayTeam')
    os_ = m.get('sectionsNo999')
    ok = (v.get('home') == oh and v.get('away') == oa)
    res['本地=官方' if ok else '本地≠官方(需翻转)'] += 1
    rows.append((mid, d, v, why, f'官方 {oh} vs {oa} {os_}', '同向' if ok else '反向'))

for k, n in res.most_common():
    print(f'  {k}: {n}')
print()
for mid, d, v, why, off, verdict in rows:
    print(f'  {mid} {d} [{why}] 本地 {v.get("home")} vs {v.get("away")} {v.get("fullScore")} | 官方 {off} | {verdict}')
