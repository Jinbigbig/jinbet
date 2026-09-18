# -*- coding: utf-8 -*-
"""缺失因素数据源可行性探测（只读，不写仓库）"""
import json, urllib.request, urllib.parse, ssl

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def get(url, headers=None, timeout=15):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.status, r.read(400000).decode('utf-8', errors='ignore')


print('=' * 78)
print('① 体彩官方 API —— 是否自带「联赛排名」（队名方括号内）')
print('=' * 78)
try:
    st, body = get('https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c',
                   {'Referer': 'https://www.sporttery.cn/jc/jsq/zqhhgg/'})
    d = json.loads(body)
    subs = (d.get('value') or {}).get('matchInfoList') or []
    n = 0
    for blk in subs:
        for m in (blk.get('subMatchList') or []):
            h = m.get('homeTeamAllName') or ''
            a = m.get('awayTeamAllName') or ''
            if n < 6:
                print(f"   {m.get('matchNumStr','')} {h}  vs  {a}   排名标记={'有' if ('[' in h or '[' in a) else '无'}")
            n += 1
    print(f'   共 {n} 场；字段清单: {sorted((subs[0]["subMatchList"][0].keys())) if n else "-"}')
except Exception as e:
    print(f'   ❌ 失败: {e}')

print()
print('=' * 78)
print('② 网易竞彩「分析/伤停」相关端点')
print('=' * 78)
for u in ['https://sports.163.com/caipiao/api/web/match/analysis/1?matchId=5502154',
          'https://sports.163.com/caipiao/api/web/match/detail/1?matchId=5502154',
          'https://sports.163.com/caipiao/api/web/match/injury/1?matchId=5502154']:
    try:
        st, b = get(u, {'Referer': 'https://sports.163.com/caipiao/match/football/jczq'}, 10)
        print(f'   {st} len={len(b)}  {u[:70]}  →  {b[:110]!r}')
    except Exception as e:
        print(f'   ❌ {u[:70]} → {type(e).__name__}: {str(e)[:70]}')

print()
print('=' * 78)
print('③ 公开足球数据源（积分榜 / xG / 伤停）')
print('=' * 78)
probes = [
    ('FotMob 赛程/伤停', 'https://www.fotmob.com/api/matches?date=20260910'),
    ('FotMob 积分榜', 'https://www.fotmob.com/api/leagues?id=47&season=2026'),
    ('Sofascore 赛程', 'https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-09-10'),
    ('Understat xG(英超)', 'https://understat.com/league/EPL/2026'),
    ('Flashscore', 'https://www.flashscore.com/'),
    ('Transfermarkt 身价', 'https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1'),
]
for name, u in probes:
    try:
        st, b = get(u, None, 15)
        print(f'   ✅ {name}: HTTP {st}, {len(b)} 字节, 片段={b[:90]!r}')
    except Exception as e:
        print(f'   ❌ {name}: {type(e).__name__} {str(e)[:80]}')
