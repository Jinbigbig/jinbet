# -*- coding: utf-8 -*-
"""主客方向体检：实时官方 API（网易竞彩）vs 本地 SCHEDULE vs 本地赛果库。

用途：results_data.json 曾因「反序双写」全库颠倒；本脚本用官方源按竞彩编号
逐场比对，可随时复查方向是否与官方一致（一致率应为 100%）。
用法: python verify_homeaway.py [回溯天数，默认45]
"""
import json, os, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
BEIJING = timezone(timedelta(hours=8))
today = datetime.now(BEIJING)
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*', 'Content-Type': 'application/x-www-form-urlencoded',
    'Accept-Encoding': 'identity', 'Referer': 'https://sports.163.com/caipiao/match/football/jczq',
}

live = {}
import sys
DAYS=int(sys.argv[1]) if len(sys.argv)>1 else 45
for d_back in range(0, DAYS):
    day = today - timedelta(days=d_back)
    ds = day.strftime('%Y-%m-%d') + ' 12:00:00'
    url = 'https://sports.163.com/caipiao/api/web/match/list/jingcai/matchList/1?days=' + urllib.parse.quote(ds)
    try:
        req = urllib.request.Request(url, data=b'', headers=headers)
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode('utf-8', errors='ignore'))
        ms = data.get('data', []) or []
    except Exception as e:
        continue
    for m in ms:
        ls = m.get('footballLiveScore') or {}
        if not (m.get('matchStatus') == 3 and ls.get('status') == '完'):
            continue
        jc = m.get('jcNum', '')
        h = (m.get('homeTeam') or {}).get('teamName', '')
        a = (m.get('guestTeam') or {}).get('teamName', '')
        if not (jc and h and a):
            continue
        live[(jc, frozenset((h, a)))] = {'home': h, 'away': a, 'jc': jc,
                                         'score': f"{ls.get('homeScore',0)}:{ls.get('guestScore',0)}"}

res = json.load(open(os.path.join(ROOT, 'results_data.json'), 'r', encoding='utf-8'))
# results 按 matchNumStr 建索引
res_by_jc = {}
for k, v in res.items():
    jc = v.get('matchNumStr', '')
    if not jc:
        continue
    res_by_jc.setdefault(jc, []).append((k, v))

print(f'实时官方(含编号) {len(live)} 场；results 带编号 {len(res_by_jc)} 个编号')
print()
print('按编号逐个对照（同一编号 = 同一场比赛）：')
print(f'{"编号":<10}{"实时官方 主vs客":<24}{"实时比分":<9}{"results key":<30}{"results比分":<9}判定')
n = 0
stat = {'same': 0, 'rev': 0}
for (jc, fs), g in sorted(live.items()):
    cand = res_by_jc.get(jc)
    if not cand:
        continue
    # 取队名集合相同的
    hit = None
    for k, v in cand:
        if frozenset(k.split('_', 2)[1:]) == fs:
            hit = (k, v); break
    if not hit:
        continue
    k, v = hit
    lh, la = v.get('home', ''), v.get('away', '')
    same = (lh, la) == (g['home'], g['away'])
    stat['same' if same else 'rev'] += 1
    if n < 0:
        print(f'{jc:<10}{g["home"]+" vs "+g["away"]:<24}{g["score"]:<9}{k:<30}{str(v.get("score") or v.get("fullScore") or ""):<9}{"一致" if same else "★颠倒"}')
        n += 1
print()
print(f'总计 {sum(stat.values())} 场：一致 {stat["same"]}，颠倒 {stat["rev"]}')
