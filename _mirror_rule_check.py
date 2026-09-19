# -*- coding: utf-8 -*-
"""用官方 API 对「跨日镜像组」做大规模规则校验（只读）。

问题：跨日孪生组该留哪一侧？
做法：对 2026-07-01~08-10 窗口，拉官方赛果，按 (日期±1, 队名) 匹配，
      统计每组里「与官方同向」的是哪一条（早的 / 晚的）。
"""
import json
import glob
import os
import re
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
    for p in range(1, 12):
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


off = q('2026-06-30', '2026-08-11')
print(f'官方 {len(off)} 场')

idx = collections.defaultdict(list)   # (date, frozenset names) -> [official]
for m in off:
    h, a = m.get('homeTeam'), m.get('awayTeam')
    if not h or not a:
        continue
    idx[(m.get('matchDate'), frozenset((h, a)))].append(m)


def same(x, y):
    if not x or not y:
        return False
    cx = re.sub(r'[\s\-]', '', str(x))
    cy = re.sub(r'[\s\-]', '', str(y))
    if cx == cy:
        return True
    if len(cx) >= 2 and len(cy) >= 2 and (cx.startswith(cy) or cy.startswith(cx)):
        return True
    return False


def find_off(date, h, a):
    for delta in (0, -1, 1):
        d = (collections.datetime.date.fromisoformat(date) if hasattr(collections, 'datetime') else None)
        try:
            import datetime as _dt
            dd = (_dt.date.fromisoformat(date) + _dt.timedelta(days=delta)).isoformat()
        except Exception:
            dd = date
        for m in idx.get((dd, frozenset((h, a))), []):
            if same(m.get('homeTeam'), h) and same(m.get('awayTeam'), a):
                return m, 'fwd'
            if same(m.get('homeTeam'), a) and same(m.get('awayTeam'), h):
                return m, 'rev'
    return None, None


groups = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(ROOT, 'results_history', '*.json'))):
    date = os.path.basename(f)[:-5]
    for k, v in json.load(open(f, encoding='utf-8')).items():
        if isinstance(v, dict):
            groups[str(v.get('matchId'))].append((date, k, v))

stat = collections.Counter()
samples = []
for mid, items in groups.items():
    if len(items) < 2:
        continue
    dates = sorted(set(x[0] for x in items))
    if len(dates) == 1:
        continue
    if dates[0] < '2026-06-30' or dates[0] > '2026-08-11':
        continue
    verdicts = []
    for d, k, v in items:
        m, way = find_off(d, v.get('home'), v.get('away'))
        verdicts.append((d, v, m, way))
    # 找与官方同向的那条
    fwd = [x for x in verdicts if x[3] == 'fwd']
    none_ = [x for x in verdicts if x[3] is None]
    if len(fwd) == 1:
        w = fwd[0]
        earliest = min(verdicts, key=lambda x: x[0])
        stat['唯一同向-早' if w[0] == earliest[0] else '唯一同向-晚'] += 1
        if w[0] != earliest[0] and len(samples) < 12:
            samples.append((mid, [(x[0], x[1].get('home'), x[1].get('away'), x[1].get('fullScore'), x[3]) for x in verdicts]))
    elif len(fwd) == 0:
        stat['无同向(匹配失败)'] += 1
    else:
        stat['多条同向'] += 1
    if any(x[3] == 'rev' for x in verdicts):
        stat['含反向命中'] += 1

print()
for k, n in stat.most_common():
    print(f'  {k}: {n}')
print()
for mid, rows in samples:
    print('-- id', mid)
    for r in rows:
        print('    ', r)
