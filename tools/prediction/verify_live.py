# -*- coding: utf-8 -*-
"""
终极判定：实时抓取官方源，与本地 results_data.json 逐场比对主客方向。
官方源 = 网易竞彩 API（与 results_data.json 的生成源同一家，字段 homeTeam/guestTeam）
如一致率≈100% → 本地库被人为反序污染（写入侧 bug），可全库修正
如一致率≈0%   → 本地库整体颠倒
"""
import json, os, urllib.request, urllib.parse, sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))

BEIJING = timezone(timedelta(hours=8))
today = datetime.now(BEIJING)
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Accept-Encoding': 'identity',
    'Referer': 'https://sports.163.com/caipiao/match/football/jczq',
}

gt = {}   # (date, frozenset(teams)) -> dict(home, away, score, jcNum)
failed = 0
for d_back in range(0, 16):
    day = today - timedelta(days=d_back)
    days_val = day.strftime('%Y-%m-%d') + ' 12:00:00'
    url = 'https://sports.163.com/caipiao/api/web/match/list/jingcai/matchList/1?days=' + urllib.parse.quote(days_val)
    try:
        req = urllib.request.Request(url, data=b'', headers=headers)
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode('utf-8', errors='ignore')
        data = json.loads(raw)
        ms = data.get('data', []) or []
    except Exception as e:
        failed += 1
        print(f'  [WARN] 拉取 {days_val} 失败: {e}')
        continue
    for m in ms:
        ls = m.get('footballLiveScore') or {}
        if not (m.get('matchStatus') == 3 and ls.get('status') == '完'):
            continue
        h = (m.get('homeTeam') or {}).get('teamName', '') or ''
        a = (m.get('guestTeam') or {}).get('teamName', '') or ''
        if not h or not a:
            continue
        mt = m.get('matchTime') or 0
        d = day.strftime('%Y-%m-%d')
        if mt:
            try:
                d = datetime.fromtimestamp(int(mt) / 1000, BEIJING).strftime('%Y-%m-%d')
            except Exception:
                pass
        sc = f"{ls.get('homeScore', 0)}:{ls.get('guestScore', 0)}"
        gt[(d, frozenset((h, a)))] = {'home': h, 'away': a, 'score': sc,
                                      'jcNum': m.get('jcNum', ''), 'src': '163-API'}

print(f'实时官方源（网易竞彩 API）已完赛场次: {len(gt)}  (失败请求 {failed} 次)')
if len(gt) < 5:
    print('  ⚠️ 样本过少，无法判定（可能网络受限）')
    sys.exit(0)

res = json.load(open(os.path.join(ROOT, 'results_data.json'), 'r', encoding='utf-8'))
print(f'本地 results_data.json 条目: {len(res)}')

same = rev = score_mismatch = 0
miss = 0
rows = []
for k, v in res.items():
    p = k.split('_', 2)
    if len(p) != 3:
        continue
    d = p[0]
    key = (d, frozenset(p[1:]))
    g = gt.get(key)
    if not g:
        miss += 1
        continue
    lh, la = v.get('home', ''), v.get('away', '')
    if (lh, la) == (g['home'], g['away']):
        same += 1
        if str(v.get('score') or v.get('fullScore') or '') != g['score']:
            score_mismatch += 1
    else:
        rev += 1
        if str(v.get('score') or v.get('fullScore') or '') != g['score'][::-1]:
            score_mismatch += 1
    if len(rows) < 12:
        rows.append((d, g['jcNum'], f"{g['home']} vs {g['away']}", g['score'],
                     f"{lh} vs {la}", str(v.get('score') or v.get('fullScore') or ''),
                     '一致' if (lh, la) == (g['home'], g['away']) else '★颠倒'))

tot = same + rev
print()
print('=' * 90)
print('比对结果（同一场比赛：官方源方向 vs 本地 results_data 方向）')
print('=' * 90)
print(f'  可比对场次      : {tot}   (本地有但官方未覆盖/未完赛: {miss})')
print(f'  方向【一致】    : {same}  ({same/max(tot,1)*100:.1f}%)')
print(f'  方向【颠倒】    : {rev}  ({rev/max(tot,1)*100:.1f}%)')
print(f'  比分也对不上的  : {score_mismatch}')
print()
print(f'  {"日期":<11}{"编号":<9}{"官方 主 vs 客":<26}{"官方比分":<9}{"本地 主 vs 客":<26}{"本地比分":<9}判定')
for r in rows:
    print(f'  {r[0]:<11}{r[1]:<9}{r[2]:<26}{r[3]:<9}{r[4]:<26}{r[5]:<9}{r[6]}')
