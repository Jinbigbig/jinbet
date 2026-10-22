#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取腾讯体育足球积分榜，补充 7M 数据库未收录的赛事（欧冠等）。

数据源（前端接口，页面 https://sports.qq.com/ucl/stats/teams 调的就是它）：
  https://matchweb.sports.qq.com/m/rank/listV2?competitionId=<id>&scene=pc_hot&limit=50
  - scene=pc_hot + limit=50 → 返回完整榜（欧冠 36 队；只给 top10 是因为默认 limit 小）
  - 字段：serial 排名 / team.name 队名 / win·draw·lost / score 积分 / goals（口径不明，不展示）

输出：qq_standings.json
  {"fetched_at": "...", "leagues": {"欧冠": {"comp_id": 5, "teams": [
      {"rank":1,"name":"巴黎圣日耳曼","p":3,"w":3,"d":0,"l":0,"pts":9}, ...]}}}

说明：腾讯榜不含进/失球，故只输出赛/胜/平/负/积分；缺数据的字段一律不编造。
"""
import gzip
import json
import sys
import urllib.request
from datetime import datetime

API = ('https://matchweb.sports.qq.com/m/rank/listV2'
       '?competitionId={cid}&scene=pc_hot&limit=50')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
      'Referer': 'https://sports.qq.com/', 'Accept-Encoding': 'gzip'}

# 赛事名 → 腾讯 competitionId（5=欧冠 已验证；其余为同接口探测所得，留作后续扩展）
COMP_MAP = {
    '欧冠': 5,
    '英超': 8,
    '意甲': 21,
    '德甲': 22,
    '西甲': 23,
    '法甲': 24,  # 18 经全量扫描无此 ID（2026-10-22 扫 1-399 实证 24=法甲）
}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'ignore'))


def fetch_league(name, cid):
    d = _get(API.format(cid=cid))
    info = ((d.get('data') or {}).get('info') or {})
    if not info:
        return None
    # child[0] = 积分榜（child[1] 是射手榜）
    for ch in info.get('child') or []:
        if ch.get('desc') == '积分榜':
            rows = ch.get('rows') or []
            break
    else:
        rows = (info.get('child') or [{}])[0].get('rows') or []
    teams = []
    for r in rows:
        w, dr, l = int(r.get('win') or 0), int(r.get('draw') or 0), int(r.get('lost') or 0)
        teams.append({
            'rank': int(r.get('serial') or 0),
            'name': (r.get('team') or {}).get('name') or '',
            'p': w + dr + l,
            'w': w, 'd': dr, 'l': l,
            'pts': int(r.get('score') or 0),
        })
    if not teams:
        return None
    return {'comp_id': cid, 'desc': info.get('desc') or name, 'teams': teams}


def main(only=None):
    out = {'fetched_at': datetime.now().isoformat(timespec='seconds'), 'leagues': {}}
    for name, cid in COMP_MAP.items():
        if only and name not in only:
            continue
        try:
            lg = fetch_league(name, cid)
        except Exception as e:
            print(f'[QQ榜] {name} 抓取失败：{type(e).__name__} {e}', file=sys.stderr)
            continue
        if not lg:
            print(f'[QQ榜] {name} 无数据（competitionId={cid}）', file=sys.stderr)
            continue
        out['leagues'][name] = lg
        print(f'[QQ榜] {name}：{len(lg["teams"])} 队（competitionId={cid}）')
    if not out['leagues']:
        print('[QQ榜] 全部失败，保留原文件不动', file=sys.stderr)
        return 1
    # 合并旧文件：单次只抓到部分联赛时不丢其余联赛
    try:
        old = json.load(open('qq_standings.json', encoding='utf-8')).get('leagues') or {}
        for k, v in old.items():
            out['leagues'].setdefault(k, v)
    except Exception:
        pass
    json.dump(out, open('qq_standings.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'[QQ榜] 已写入 qq_standings.json：{", ".join(out["leagues"])}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or None))
