#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""网易红彩「数据」tab 采集 → hongcai.json

数据链路：
  scripts/matches_data.json（当日竞彩场次，顶层 matchId 就是红彩 matchInfoId，
  同一套网易编号体系，无需按队名模糊匹配）
    → /api/front/matchInfo/v5/data/compare/{id}
      统计对比 / 风格指数 / 裁判执法 / 比赛地天气 / 盘路走势 / 交锋统计 /
      进球时段分布 / 主客分项战绩
    → /api/front/matchInfo/v5/analyse/{id}
      赛前分析短句（含 <span> 标签，清洗为纯文本）/ 伤停名单（带位置与伤情）
    → hongcai.json（按竞彩编号索引，matlas import 与 _gen_report 共用同一份）

口径说明：
  · matchId 与红彩 matchInfoId 同一编号体系，compare.matchInfo.jcNum（周一001）
    再兜底校准一次，确保编号与场次严格对应，不靠队名猜。
  · 红彩的 winGameRate / winPlateRate / bigGameRate 是 0~1 小数，这里统一
    转成百分数（整数），下游直接展示，不必各自再乘 100。
  · goalDistList 的 scored / conceded 是内嵌 JSON 字符串，元素为
    [占比%, 个数, 起始分钟, 结束分钟]，这里拆成 {pct, n, from, to}。
  · 盘路 / 交锋的 listResultList 是 [3,1,0]（胜/平/负），转成 "WDL" 序列。
  · 伤停 onPlay：受伤 → out，停赛 → suspended；state 作伤情说明（肌肉受伤等）。
  · ELO 曲线需付费订阅，不采集。

用法：
  python _fetch_hongcai.py               # 采当日全部场次
  python _fetch_hongcai.py --date 2026-11-03
  python _fetch_hongcai.py --only 周一001,周一002
  python _fetch_hongcai.py --raw out.json   # 附带保存原始接口响应
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import date as _date

BASE = 'https://hongcai.163.com'
MATCHES = 'scripts/matches_data.json'
OUT = 'hongcai.json'
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) '
                   'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'),
    'Referer': 'https://hongcai.163.com/vuehtml/compare/',
    'Accept': 'application/json, text/plain, */*',
}

# 盘路 / 交锋的 8 个维度（红彩字段名 → 本站风格 key）
DISH_KEYS = (
    ('homeSame6', 'home6'), ('homeSame12', 'home12'),
    ('allTeam6', 'all6'), ('allTeam12', 'all12'),
    ('leagueSame6', 'lg6'), ('leagueSame12', 'lg12'),
    ('homeAndLeagueSame6', 'home_lg6'), ('homeAndLeagueSame12', 'home_lg12'),
)

# 统计对比 10 项（红彩字段名 → 本站 key）
STAT_KEYS = (
    ('possessionPct', 'possession'), ('shotsPerMatch', 'shots'),
    ('shotsAgainstPerMatch', 'shots_against'), ('cornersPerMatch', 'corners'),
    ('foulsPerMatch', 'fouls'), ('freeKicksPerMatch', 'freekicks'),
    ('yellowCardsPerMatch', 'yellow'), ('redCardsPerMatch', 'red'),
    ('goalEfficiency', 'attack_eff'), ('defenseEfficiency', 'defense_eff'),
)

# 风格指数 7 维（红彩 goal 即进攻）
STYLE_KEYS = (
    ('goal', 'attack'), ('defense', 'defense'), ('possession', 'possession'),
    ('duel', 'duel'), ('discipline', 'discipline'), ('value', 'value'),
    ('overall', 'overall'),
)

RE_TAG = re.compile(r'<[^>]+>')
RE_FIRST_NUM = re.compile(r'-?\d+(?:\.\d+)?')


def api(path: str, tries: int = 3):
    """GET 一个红彩接口，返回 data 字段；失败重试后抛异常。"""
    url = BASE + path if path.startswith('/') else f'{BASE}/{path}'
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
            if payload.get('code') != 200:
                raise RuntimeError(f"code={payload.get('code')}: {payload.get('message')}")
            return payload.get('data')
        except Exception as e:  # noqa: BLE001 - 网络抖动重试，末次抛出
            last = e
            if i + 1 < tries:
                time.sleep(1.5 * (i + 1))
    raise last  # type: ignore[misc]


def soft(path: str):
    """单接口失败不阻塞整体：返回 (data, err)。"""
    try:
        return api(path), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def emb(v):
    """红彩部分字段是「内嵌 JSON 字符串」，且常再包一层 {"compareData": "..."}。"""
    if isinstance(v, dict) and v.get('compareData') is not None:
        v = v.get('compareData')
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return {}
    return v or {}


def pct100(v) -> int | None:
    """0~1 小数 → 百分数整数。"""
    try:
        return round(float(v) * 100)
    except (TypeError, ValueError):
        return None


def num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 2)
    except (TypeError, ValueError):
        return None


def first_num(v):
    """从「12°C」「64%」「3.7m/s」这类带单位字符串里取数字。"""
    if isinstance(v, (int, float)):
        return num(v)
    m = RE_FIRST_NUM.search(str(v or ''))
    return num(m.group()) if m else None


def seq_of(arr) -> str:
    """[3,1,0] → "WDL"。"""
    m = {'3': 'W', '1': 'D', '0': 'L'}
    return ''.join(m.get(str(x), '') for x in (arr or []))


def norm_bucket(b: dict | None) -> dict | None:
    """盘路/交锋的单维度：多场统计 + 胜平负序列。"""
    if not isinstance(b, dict) or not b:
        return None
    n = num(b.get('matchNum'))
    if not n:
        return None
    return {
        'n': n,
        'w': num(b.get('winNum')) or 0,
        'd': num(b.get('dogfallNum')) or 0,
        'l': num(b.get('loserNum')) or 0,
        'win_rate': pct100(b.get('winGameRate')),
        'plate_rate': pct100(b.get('winPlateRate')),
        'big_rate': pct100(b.get('bigGameRate')),
        'gf': num(b.get('goalNum')),
        'ga': num(b.get('ballverlustNum')),
        'seq': seq_of(b.get('listResultList')),
    }


def norm_stat_list(items, id_keys: tuple) -> dict:
    """把 dishList / meetingList（[{teamId, ...8 维}]）整理成 {home|away: {key: bucket}}。"""
    out = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        tid = it.get('teamId')
        side = 'home' if tid == id_keys[0] else ('away' if tid == id_keys[1] else None)
        if not side:
            continue
        got = {}
        for src, key in DISH_KEYS:
            b = norm_bucket(it.get(src))
            if b:
                got[key] = b
        if got:
            out[side] = got
    return out


def norm_goal_dist(items, id_keys: tuple) -> dict:
    """进球时段分布 → {home|away: {scored: [...], conceded: [...]}}。"""
    out = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        tid = it.get('teamId')
        side = 'home' if tid == id_keys[0] else ('away' if tid == id_keys[1] else None)
        if not side:
            continue
        got = {}
        for kind in ('scored', 'conceded'):
            arr = emb(it.get(kind))
            if not isinstance(arr, list):
                continue
            rows = []
            for x in arr:
                if not isinstance(x, list) or len(x) < 4:
                    continue
                # 实测口径：[个数, 占比%, 起始分钟, 结束分钟]
                rows.append({'n': num(x[0]), 'pct': num(x[1]),
                             'from': num(x[2]), 'to': num(x[3])})
            if rows:
                got[kind] = rows
        if got:
            out[side] = got
    return out


def norm_ref_stats(b: dict | None) -> dict | None:
    """裁判执法战绩：场次/胜平负 + 场均黄红点。"""
    if not isinstance(b, dict) or not b:
        return None
    n = num(b.get('matchCount'))
    if not n:
        return None
    return {
        'n': n,
        'w': num(b.get('winCount')) or 0,
        'd': num(b.get('drawCount')) or 0,
        'l': num(b.get('lossCount')) or 0,
        'yellow': num(b.get('averageYellowCard')),
        'red': num(b.get('averageRedCard')),
        'pen': num(b.get('averagePenalty')),
    }


def norm_wx_stats(b: dict | None) -> dict | None:
    """某天气等级下的战绩（红彩 winRate 已是百分数，不再乘 100）。"""
    if not isinstance(b, dict) or not b:
        return None
    n = num(b.get('matchCount'))
    if not n:
        return None
    return {
        'n': n,
        'w': num(b.get('winCount')) or 0,
        'd': num(b.get('drawCount')) or 0,
        'l': num(b.get('lossCount')) or 0,
        'win_rate': first_num(b.get('winRate')),
    }


def norm_injuries(rows) -> list[dict]:
    """伤停名单：onPlay 受伤→out / 停赛→suspended，state 作伤情。"""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        name = str(r.get('playerName') or '').strip()
        if not name:
            continue
        play = str(r.get('onPlay') or '').strip()
        state = str(r.get('state') or '').strip()
        # 红彩的 onPlay 只分「受伤 / 停赛」两类，轮休也被归到停赛里，
        # 用 state 再校正一次：轮休算缺阵、state 明确写停赛的才算停赛。
        if '轮休' in state:
            status = 'out'
        elif '停赛' in play or '停赛' in state:
            status = 'suspended'
        elif '伤' in play or '伤' in state:
            status = 'out'
        else:
            status = 'doubt'
        out.append({
            'name': name,
            'position': str(r.get('position') or '').strip(),
            'status': status,
            'state': state,
        })
    return out


def clean_lines(rows) -> list[str]:
    """赛前分析短句：去 HTML 标签、去空行、去重。"""
    out, seen = [], set()
    for r in rows or []:
        txt = RE_TAG.sub('', str((r or {}).get('content') or '')).strip()
        txt = re.sub(r'\s+', ' ', txt)
        if txt and txt not in seen:
            seen.add(txt)
            out.append(txt)
    return out


def fetch_one(info: dict) -> dict:
    """采一场：数据对比 + 赛前分析。info 来自 matches_data.json 的单场。"""
    hc_id = int(info['matchId'])
    cmp_data, err = soft(f'/api/front/matchInfo/v5/data/compare/{hc_id}')
    if err:
        raise RuntimeError(f'数据对比失败: {err}')
    cmp_data = cmp_data or {}
    ana, a_err = soft(f'/api/front/matchInfo/v5/analyse/{hc_id}')
    ana = ana or {}

    mi = cmp_data.get('matchInfo') or {}
    hid, gid = mi.get('homeId'), mi.get('guestId')
    stats = cmp_data.get('statsCompare') or {}
    style = cmp_data.get('styleCompare') or {}
    rng = cmp_data.get('range') or {}

    def _side_stat(blk):
        got = {}
        for src, key in STAT_KEYS:
            v = num((blk or {}).get(src))
            if v is not None:
                got[key] = v
        return got

    def _side_style(blk):
        got = {}
        for src, key in STYLE_KEYS:
            v = num((blk or {}).get(src))
            if v is not None:
                got[key] = v
        return got

    def _side_range(blk):
        got = {}
        for src, key in (('game', 'n'), ('win', 'w'), ('draw', 'd'), ('loss', 'l'),
                         ('score', 'gf'), ('lossScore', 'ga'),
                         ('rank', 'rank'), ('point', 'pts'), ('scoreDiff', 'gd')):
            v = num((blk or {}).get(src))
            if v is not None:
                got[key] = v
        return got

    # range 四象限：主/客队 × 赛季总/主场/客场。全季只有 total，
    # 主客分项各只有 4 场左右的小样本，两套口径分开存，不混用。
    ht_rng = rng.get('homeTeam') or {}
    gt_rng = rng.get('guestTeam') or {}
    range_out = {
        'home_total': _side_range(ht_rng.get('total')),
        'away_total': _side_range(gt_rng.get('total')),
        'home_home': _side_range(ht_rng.get('home')),
        'home_guest': _side_range(ht_rng.get('guest')),
        'away_home': _side_range(gt_rng.get('home')),
        'away_guest': _side_range(gt_rng.get('guest')),
    }
    # 兼容旧键：home=主队主场、away=客队客场（下游按这两键取「同主客」口径）
    range_out['home'] = range_out['home_home']
    range_out['away'] = range_out['away_guest']

    ref = emb(cmp_data.get('refereeCompare'))
    wx = emb(cmp_data.get('weatherCompare'))
    referee = None
    if ref.get('nameZh') or ref.get('nameEn'):
        referee = {
            'name': str(ref.get('nameZh') or ref.get('nameEn') or '').strip(),
            'name_en': str(ref.get('nameEn') or '').strip(),
            'career': norm_ref_stats(ref.get('overall')),
            'by_home': norm_ref_stats(ref.get('homeTeam')),
            'by_away': norm_ref_stats(ref.get('guestTeam')),
        }
    weather = None
    if wx.get('weatherName') or wx.get('temperature') is not None:
        # 红彩风速单位 m/s，站内 Open-Meteo 用 km/h，统一折算成 km/h 便于对比替换
        wind_ms = first_num(wx.get('wind'))
        weather = {
            'name': str(wx.get('weatherName') or '').strip(),
            'temperature': first_num(wx.get('temperature')),
            'humidity': first_num(wx.get('humidity')),
            'wind': round(wind_ms * 3.6) if wind_ms is not None else None,
            'by_home': norm_wx_stats(wx.get('homeTeam')),
            'by_away': norm_wx_stats(wx.get('guestTeam')),
        }

    out = {
        'hc_id': hc_id,
        'jc_num': str(mi.get('jcNum') or info.get('matchNumStr') or '').strip(),
        'league': str((cmp_data.get('leagueMatch') or {}).get('leagueName')
                      or info.get('league') or '').strip(),
        'kickoff': str(mi.get('matchTime') or '').strip(),
        'home': str((mi.get('homeMatchTeam') or {}).get('teamName') or info.get('home') or '').strip(),
        'away': str((mi.get('guestMatchTeam') or {}).get('teamName') or info.get('away') or '').strip(),
        'stats': {'home': _side_stat(stats.get('home')), 'away': _side_stat(stats.get('away'))},
        'style': {'home': _side_style(style.get('home')), 'away': _side_style(style.get('away'))},
        'range': range_out,
        'referee': referee,
        'weather': weather,
        'dish': norm_stat_list(cmp_data.get('dishList'), (hid, gid)),
        'meeting': norm_stat_list(cmp_data.get('meetingList'), (hid, gid)),
        'goal_dist': norm_goal_dist(cmp_data.get('goalDistList'), (hid, gid)),
        'analyse': {
            'home': clean_lines(ana.get('homeAnalyseVo')),
            'guest': clean_lines(ana.get('guestAnalyseVo')),
        },
        'injuries': {
            'home': norm_injuries(ana.get('homeInjure')),
            'guest': norm_injuries(ana.get('guestInjure')),
        },
    }
    if a_err:
        out['_warn'] = f'赛前分析缺失: {a_err}'
    return out


def _sched_day() -> str:
    """取 matches_data.json 自带的报告日。

    系统日期不可靠：凌晨到上午这段时间已经跨到开赛日，而报告日仍是前一天
    （例：周二 09:35 跑，场次是「周一001」，报告日应为周一）。用报告日
    才能让 matlas / _gen_report 的日期校验对得上。
    """
    try:
        with open(MATCHES, encoding='utf-8') as f:
            return str((json.load(f) or {}).get('today') or '')[:10]
    except Exception:  # noqa: BLE001
        return ''


def load_schedule(day: str | None) -> list[dict]:
    try:
        with open(MATCHES, encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f'读取 {MATCHES} 失败: {e}', file=sys.stderr)
        return []
    if day and str(d.get('today') or '')[:10] not in ('', day):
        print(f'⚠️ {MATCHES} 的 today={d.get("today")} 与请求日期 {day} 不一致，'
              f'仍按文件内容采集', file=sys.stderr)
    return [m for m in (d.get('matches') or []) if str(m.get('matchId') or '').isdigit()]


def main() -> None:
    ap = argparse.ArgumentParser(description='网易红彩数据tab采集 → hongcai.json')
    ap.add_argument('--date', default=None, help='日期（仅用于校核 matches_data.json，默认今天）')
    ap.add_argument('--only', default='', help='只采指定编号，逗号分隔，如 周一001,周一002')
    ap.add_argument('--raw', default='', help='同时保存原始接口响应到该文件')
    args = ap.parse_args()

    today = args.date or _sched_day() or _date.today().isoformat()
    sched = load_schedule(today)
    only = {x.strip() for x in args.only.split(',') if x.strip()}
    if only:
        sched = [m for m in sched if m.get('matchNumStr') in only]
    if not sched:
        print('今日无场次可采')
        return

    matches: dict[str, dict] = {}
    raw_all: dict[str, dict] = {}
    miss: list[str] = []
    for m in sched:
        num_s = str(m.get('matchNumStr') or '')
        try:
            got = fetch_one(m)
        except Exception as e:  # noqa: BLE001 - 单场失败只记缺失
            miss.append(f'{num_s} {m.get("home")}vs{m.get("away")}: {e}')
            print(f'  ✗ {num_s} {m.get("home")} vs {m.get("away")} — {e}')
            continue
        key = got.get('jc_num') or num_s
        if key != num_s:
            print(f'  ⚠️ {num_s} 红彩返回编号 {key}，按 matches_data 的编号归档', file=sys.stderr)
            key = num_s
        matches[key] = got
        st = got['stats']['home']
        print(f'  ✓ {num_s} {got["home"]} vs {got["away"]} — '
              f'统计 {len(st)} 项 / 伤停 {len(got["injuries"]["home"])}+'
              f'{len(got["injuries"]["guest"])} / 分析 '
              f'{len(got["analyse"]["home"])}+{len(got["analyse"]["guest"])} 条'
              + (f' / ⚠️ {got["_warn"]}' if got.get('_warn') else ''))
        raw_all[key] = got
        time.sleep(0.4)

    payload = {
        'updated': time.strftime('%Y-%m-%d %H:%M'),
        'date': today,
        'source': '网易红彩',
        'count': len(matches),
        'matches': matches,
        'missing': miss,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f'\n已写入 {OUT}：{len(matches)}/{len(sched)} 场'
          + (f'，缺失 {len(miss)} 场' if miss else ''))
    if args.raw:
        with open(args.raw, 'w', encoding='utf-8') as f:
            json.dump(raw_all, f, ensure_ascii=False, indent=1)
        print(f'原始响应已保存 {args.raw}')


if __name__ == '__main__':
    main()
