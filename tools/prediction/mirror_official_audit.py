# -*- coding: utf-8 -*-
"""跨月大样本官方审计：每个跨日孪生组，哪一侧与官方方向一致？（只读）"""
import json
import glob
import os
import re
import time
import datetime
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
    out, total = [], None
    for p in range(1, 20):
        url = (f'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
               f'?matchBeginDate={a}&matchEndDate={b}&leagueId=&pageSize=100&pageNo={p}'
               f'&isFix=0&matchPage=1&pcOrWap=1')
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40).read().decode('utf-8'))
        except Exception as e:
            print('  err', a, b, p, e)
            break
        v = d.get('value', {}) or {}
        ms = v.get('matchResult') or []
        if total is None:
            total = v.get('total')
        out += ms
        if len(ms) < 100:
            break
        time.sleep(0.15)
    return out, total


def same(x, y):
    if not x or not y:
        return False
    cx = re.sub(r'[\s\-（）()]', '', str(x))
    cy = re.sub(r'[\s\-（）()]', '', str(y))
    if cx == cy:
        return True
    return len(cx) >= 2 and len(cy) >= 2 and (cx.startswith(cy) or cy.startswith(cx))


off = []
_starts = []
_s = datetime.date(2025, 12, 28)
while _s <= datetime.date(2026, 9, 1):
    _starts.append(_s.isoformat())
    _s += datetime.timedelta(days=10)
for start in _starts:
    a = start
    b = (datetime.date.fromisoformat(a) + datetime.timedelta(days=9)).isoformat()
    ms, total = q(a, b)
    off += ms
    print(f'  {a}~{b}: 返回 {len(ms)} (total={total})')
print('官方累计', len(off))

idx = collections.defaultdict(list)
for m in off:
    h, a = m.get('homeTeam'), m.get('awayTeam')
    if h and a:
        idx[(m.get('matchDate'), frozenset((h, a)))].append(m)


def find_off(date, h, a):
    for delta in (0, -1, 1, -2, 2):
        try:
            dd = (datetime.date.fromisoformat(date) + datetime.timedelta(days=delta)).isoformat()
        except Exception:
            continue
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
by_month = collections.defaultdict(collections.Counter)
for mid, items in groups.items():
    if len(items) < 2:
        continue
    dates = sorted(set(x[0] for x in items))
    if len(dates) == 1:
        continue
    verd = [(d, v, *find_off(d, v.get('home'), v.get('away'))) for d, k, v in items]
    fwd = [x for x in verd if x[3] == 'fwd']
    rev = [x for x in verd if x[3] == 'rev']
    early = min(verd, key=lambda x: x[0])
    mon = dates[0][:7]
    if len(fwd) == 1:
        which = '早' if fwd[0][0] == early[0] else '晚'
        stat[f'同向在{which}'] += 1
        by_month[mon][f'同向在{which}'] += 1
    elif len(fwd) == 0 and rev:
        # 两条都与官方反向（不可能）→ 记异常
        stat['两条都反向'] += 1
        by_month[mon]['两条都反向'] += 1
    else:
        stat['无法匹配'] += 1
        by_month[mon]['无法匹配'] += 1

print()
for k, n in stat.most_common():
    print(f'  {k}: {n}')
print()
print('按月份：')
for mon in sorted(by_month):
    print(f'  {mon}: {dict(by_month[mon])}')
