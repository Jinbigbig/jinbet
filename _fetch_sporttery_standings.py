#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取中国体育彩票足球联赛资料积分榜（体彩官方口径，全量联赛）。

接口（页面 https://www.sporttery.cn/zqlszl/?showType=2&uniformLeagueId=69&seasonId=14602
的前端 zqIndex.js 调用的就是它）：

  1) 联赛/赛季清单：
     https://webapi.sporttery.cn/gateway/uniform/football/league/getLeagueListV1.qry
     返回 value.hot / value.normal[].countryList[].leagueList[] / value.other，
     每项含 leagueAbbCnName / uniformLeagueId / seasonList[{seasonId,seasonName}]。
  2) 积分榜：
     https://webapi.sporttery.cn/gateway/uniform/football/league/getTablesV2.qry
        ?seasonId=<赛季>&uniformLeagueId=<联赛>
     返回 value.totalTables[].groups[].tables[]：排名 / 场次 / 胜平负 / 进失球 / 积分。

默认抓取清单内全部联赛（各取最新赛季），输出 sporttery_standings.json，
结构与 qq/fox/uefa 三源对齐：
  {"fetched_at": "...", "source": "...", "leagues": {"英超": {"type": "league",
    "groups": [{"name": "...", "teams": [
      {"rank":1,"name":"阿森纳","p":6,"w":4,"d":1,"l":1,"gf":10,"ga":6,
       "pts":13,"group":"..."}]}]}}}
只取总榜 totalTables；homeTables/awayTables 不落地。队名已是大陆简体，无需繁简归一。

命令行可传入联赛名仅抓部分，例如：python _fetch_sporttery_standings.py 英超 西甲
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime

API = ('https://webapi.sporttery.cn/gateway/uniform/football/league/'
       'getTablesV2.qry?{qs}')
LEAGUE_LIST_API = ('https://webapi.sporttery.cn/gateway/uniform/football/league/'
                   'getLeagueListV1.qry')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
      'Referer': 'https://www.sporttery.cn/',
      'Accept': 'application/json, text/plain, */*'}
OUT = 'sporttery_standings.json'


def _int(v) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))


def fetch_league_list():
    """枚举全部联赛并各取最新赛季，返回 [(名称, uniformLeagueId, seasonId), ...]。

    顺序 hot → normal → other，同名/同 ID 去重（先到先得，hot 优先级最高）。
    """
    d = _get(LEAGUE_LIST_API)
    if str(d.get('errorCode')) != '0':
        raise RuntimeError(f'联赛列表 errorCode={d.get("errorCode")}')
    value = d.get('value') or {}
    out, seen_names, seen_ids = [], set(), set()
    for grp in ('hot', 'normal', 'other'):
        for x in (value.get(grp) or []):
            if grp == 'normal':
                cands = []
                for c in (x.get('countryList') or []):
                    cands.extend(c.get('leagueList') or [])
            else:
                cands = [x]
            for lg in cands:
                name = str(lg.get('leagueAbbCnName') or '').strip()
                lid = _int(lg.get('uniformLeagueId'))
                ss = lg.get('seasonList') or []
                if not name or not lid or not ss:
                    continue
                sid = _int(ss[0].get('seasonId'))
                if not sid or name in seen_names or lid in seen_ids:
                    continue
                seen_names.add(name)
                seen_ids.add(lid)
                out.append((name, lid, sid))
    return out


def fetch_league(name, league_id, season_id):
    qs = urllib.parse.urlencode({
        'seasonId': season_id, 'uniformLeagueId': league_id,
    })
    d = _get(API.format(qs=qs))
    if str(d.get('errorCode')) != '0':
        raise RuntimeError(f'接口 errorCode={d.get("errorCode")}')
    value = d.get('value') or {}
    groups = []
    for phase in value.get('totalTables') or []:
        phase_name = str(phase.get('phaseName') or '').strip()
        for g in phase.get('groups') or []:
            gname = str(g.get('groupName') or '').strip()
            label = ' '.join(x for x in (phase_name, gname) if x)
            teams = []
            for r in g.get('tables') or []:
                team = str(r.get('abbCnName') or '').strip()
                if not team:
                    continue
                teams.append({
                    'rank': _int(r.get('ranking')),
                    'name': team,
                    'p': _int(r.get('totalLegCnt')),
                    'w': _int(r.get('winGoalMatchCnt')),
                    'd': _int(r.get('drawMatchCnt')),
                    'l': _int(r.get('lossGoalMatchCnt')),
                    'gf': _int(r.get('goalCnt')),
                    'ga': _int(r.get('lossGoalCnt')),
                    'pts': _int(r.get('points')),
                    'group': label,
                })
            if teams:
                groups.append({'name': label, 'teams': teams})
    if not groups:
        return None
    return {'type': 'league', 'groups': groups,
            '_n': sum(len(g['teams']) for g in groups)}


def main(only=None):
    out = {'fetched_at': datetime.now().isoformat(timespec='seconds'),
           'source': '中国体育彩票 足球联赛资料 getTablesV2（totalTables）',
           'leagues': {}}
    try:
        leagues = fetch_league_list()
    except Exception as e:
        print(f'[体彩榜] 联赛清单抓取失败：{type(e).__name__} {e}', file=sys.stderr)
        return 1
    print(f'[体彩榜] 联赛清单 {len(leagues)} 项')
    ok = 0
    for name, lid, sid in leagues:
        if only and name not in only:
            continue
        try:
            lg = fetch_league(name, lid, sid)
        except Exception as e:
            print(f'[体彩榜] {name} 抓取失败：{type(e).__name__} {e}',
                  file=sys.stderr)
            continue
        if not lg:
            print(f'[体彩榜] {name} 无数据（league={lid} season={sid}）',
                  file=sys.stderr)
            continue
        out['leagues'][name] = lg
        ok += 1
        print(f'[体彩榜] {name}：{lg["_n"]} 队 / {len(lg["groups"])} 组')
    if not out['leagues']:
        print('[体彩榜] 全部失败，保留原文件不动', file=sys.stderr)
        return 1
    try:
        old = json.load(open(OUT, encoding='utf-8')).get('leagues') or {}
        for k, v in old.items():
            out['leagues'].setdefault(k, v)
    except Exception:
        pass
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f'[体彩榜] 已写入 {OUT}：本次成功 {ok} 项，合计 {len(out["leagues"])} 联赛')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or None))
