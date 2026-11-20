#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""未来赛程抓取：竞彩在售期次 + 全量赛程库（今天起 7 天）。

两条数据源：
  A. 竞彩官方 getMatchCalculatorV1 —— 只返 2 个营业日的可投注场次，用来给场次
     打「竞彩」标记（jc=1），也是编号 / 预测数据的对接口径。
  B. 竞彩参考站按日期赛程接口 —— 全量赛程库，含大量竞彩未开售的联赛；
     GET /bi-sai-lie-biao/ 拿日期条与 nonce，再按日期 POST admin-ajax.php
     取当日全部场次。今天起 7 天（今天 + 后 6 天）。

两源按「日期 + 主客队名」双向包含匹配合并：匹配上的补竞彩编号并标 jc=1，
竞彩有而全量库没有的单独追加，全量库独有的标 jc=0（页面显示「仅赛程」）。
参考站接口失败时自动降级为纯竞彩数据，保证比赛列表页不会开天窗。

产物 fixtures.json：
    {"updated": "...", "source": "jc+full",
     "days": {"2026-11-09": [{"code": "", "time": "00:00", "league": "挪超",
                              "home": "...", "away": "...", "jc": 0,
                              "fid": 1494797, "st": "未开赛"}, ...]}}

用法：
    python _fetch_fixtures.py            # 抓一次
    python _fetch_fixtures.py --dry-run  # 只打印不写盘
    python _fetch_fixtures.py --jc-only  # 跳过全量赛程（应急降级）
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

BASE = Path(__file__).resolve().parent
OUT = BASE / "fixtures.json"
JC_KEEP_DAYS = 3        # 竞彩在售只留今天起 3 个营业日
FUTURE_DAYS = 7         # 全量赛程覆盖今天 + 后 6 天

WP = "https://www.qiuxiaoce.com"
LIST_URL = f"{WP}/bi-sai-lie-biao/"
AJAX_URL = f"{WP}/wp-admin/admin-ajax.php"
UA = {"User-Agent": "Mozilla/5.0", "Referer": LIST_URL,
      "Accept": "*/*", "Origin": WP}
POST_HEADERS = {"Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest"}

# 竞彩官方联赛资料（zqlszl）：赛程赛果按联赛 + 日期区间取，补未开售场次
ZQL_LEAGUES = ('https://webapi.sporttery.cn/gateway/uniform/football/league/'
               'getLeagueListV1.qry')
ZQL_MATCHES = ('https://webapi.sporttery.cn/gateway/uniform/football/league/'
               'getMatchResultV1.qry?{qs}')
ZQL_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
               'Referer': 'https://www.sporttery.cn/',
               'Accept': 'application/json, text/plain, */*'}

sys.path.insert(0, str(BASE))
from update_odds_net import canonical_team_name, fetch_odds_from_lottery  # noqa: E402


# ---------------- A. 竞彩在售期次 ----------------

def parse_jc(text: str) -> dict[str, list[dict]]:
    """接口原文 → {营业日: [场次]}；队名归一，编号/时间/联赛原样保留。"""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}
    value = data.get("value") or {}
    out: dict[str, list[dict]] = {}
    for grp in value.get("matchInfoList") or []:
        date = str(grp.get("businessDate") or "").strip()
        if not date:
            continue
        rows = []
        for m in grp.get("subMatchList") or []:
            home = (m.get("homeTeamAbbName") or m.get("homeTeamAllName") or "").strip()
            away = (m.get("awayTeamAbbName") or m.get("awayTeamAllName") or "").strip()
            if not home or not away:
                continue
            rows.append({
                "code": str(m.get("matchNumStr") or "").strip(),
                "time": str(m.get("matchTime") or "")[:5],
                "league": str(m.get("leagueAbbName") or m.get("leagueAllName") or "").strip(),
                "home": canonical_team_name(home),
                "away": canonical_team_name(away),
                "status": str(m.get("matchStatus") or "").strip(),
                "mid": m.get("matchId"),
            })
        if rows:
            rows.sort(key=lambda r: (r["time"], r["code"]))
            out[date] = rows
    return out


# ---------------- B. 全量赛程库 ----------------

def http(url: str, data: dict | None = None, timeout: int = 30) -> str:
    body = urllib.parse.urlencode(data).encode() if data else None
    headers = dict(UA)
    if data:
        headers.update(POST_HEADERS)
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def schedule_days() -> tuple[str, list[str]]:
    """列表页拿 nonce 与日期条，只保留今天起 FUTURE_DAYS 天。"""
    h = http(LIST_URL)
    # 页面里有多个插件的 nonce，只认 abv2_ms_vars 里那一个，取错会 403
    m = re.search(r'abv2_ms_vars\s*=\s*\{[^}]*?"nonce"\s*:\s*"([^"]+)"', h)
    if not m:
        raise RuntimeError("未取到赛程接口 nonce")
    dates = re.findall(r'class="ms-dtab[^"]*"\s+data-date="(\d{4}-\d{2}-\d{2})"', h)
    if not dates:
        raise RuntimeError("未取到日期条")
    today = dt.date.today()
    end = today + dt.timedelta(days=FUTURE_DAYS)
    keep = [d for d in sorted(set(dates)) if today <= dt.date.fromisoformat(d) < end]
    return m.group(1), keep


def team_logo_ids(card: str) -> tuple[str, str]:
    """从比赛卡里取主客队的队徽编号（wp-content/logo/teams/<id>.png）。

    有的场次上游也没图，返回空串，渲染层再退回站内队名映射。
    """
    ids: dict[str, str] = {}
    pat = (r'class="ms-team (home|away)"[^>]*>(.*?)'
           r'(?=class="ms-team |class="ms-score-box"|class="ms-extra"|$)')
    for m in re.finditer(pat, card, re.S):
        lm = re.search(r'/logo/teams/(\d+)\.png', m.group(2))
        ids[m.group(1)] = lm.group(1) if lm else ""
    return ids.get("home", ""), ids.get("away", "")


def parse_cards(frag: str) -> list[dict]:
    """赛程接口返回的 HTML 片段 → 场次列表。"""
    out = []
    for c in re.split(r'(?=<div class="ms-card)', frag)[1:]:
        t = re.search(r'class="ms-time">([^<]*)<', c)
        lg = re.search(r'class="ms-league" title="([^"]+)"', c)
        st = re.search(r'class="ms-status[^"]*">([^<]*)<', c)
        fid = re.search(r'data-fid="(\d+)"', c)
        teams = dict(re.findall(r'class="ms-team (home|away)" title="([^"]+)"', c))
        home, away = teams.get("home", "").strip(), teams.get("away", "").strip()
        # 赛程库里主客队未定的场次会写成「主队 / 待定」，不进列表
        tbd = {"主队", "客队", "待定", "待确认", "tbd", "tbc", "TBD", "TBC", "-"}
        if not home or not away or home in tbd or away in tbd:
            continue
        hid, aid = team_logo_ids(c)
        out.append({
            "code": "",
            "time": (t.group(1).strip() if t else "")[:5] or "—",
            "league": lg.group(1).strip() if lg else "",
            "home": home,
            "away": away,
            "hid": hid,
            "aid": aid,
            "jc": 0,
            "fid": int(fid.group(1)) if fid else None,
            "st": (st.group(1).strip() if st else "") or "未开赛",
        })
    return out


def fetch_full() -> dict[str, list[dict]]:
    nonce, dates = schedule_days()
    out: dict[str, list[dict]] = {}
    for d in dates:
        try:
            raw = http(AJAX_URL, {"action": "abv2_ms_get_schedule",
                                  "nonce": nonce, "date": d})
            j = json.loads(raw)
            if not j.get("success"):
                print(f"[fixtures] {d} 接口返回失败，跳过")
                continue
            rows = parse_cards((j.get("data") or {}).get("html") or "")
            if rows:
                rows.sort(key=lambda r: (r["time"], r["league"], r["home"]))
                out[d] = rows
        except Exception as e:
            print(f"[fixtures] {d} 抓取异常 {type(e).__name__}: {e}，跳过")
    return out


# ---------------- C. 竞彩官方联赛资料（zqlszl 赛程赛果） ----------------

def zql_get(url: str, timeout: int = 25) -> dict:
    with urllib.request.urlopen(
            urllib.request.Request(url, headers=ZQL_HEADERS), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))


def zql_leagues() -> list[dict]:
    """联赛清单：按 ID 去重，各取最新赛季。"""
    d = zql_get(ZQL_LEAGUES)
    if str(d.get('errorCode')) != '0':
        raise RuntimeError(f'联赛清单 errorCode={d.get("errorCode")}')
    value = d.get('value') or {}
    out: list[dict] = []
    seen: set[int] = set()
    for grp in ('hot', 'normal', 'other'):
        for x in value.get(grp) or []:
            if grp == 'normal':
                leagues = [lg for c in x.get('countryList') or []
                           for lg in c.get('leagueList') or []]
            else:
                leagues = [x]
            for lg in leagues:
                lid = lg.get('uniformLeagueId')
                seasons = lg.get('seasonList') or []
                if not lid or not seasons:
                    continue
                key = int(lid)
                if key in seen:
                    continue
                seen.add(key)
                season = max(seasons, key=lambda s: int(s.get('seasonId') or 0))
                name = str(lg.get('leagueAbbCnName')
                           or lg.get('leagueAllCnName') or '').strip()
                if name:
                    out.append({'name': name, 'lid': key,
                                'sid': int(season.get('seasonId') or 0)})
    return out


def zql_status(v) -> str:
    s = str(v or '').strip() or '未开赛'
    if '未开始' in s or '待开赛' in s:
        return '未开赛'
    if '已完成' in s or '已结束' in s:
        return '已完赛'
    return s


def zql_rows(league: dict, dates: set[str]) -> dict[str, list[dict]]:
    qs = urllib.parse.urlencode({
        'seasonId': league['sid'], 'uniformLeagueId': league['lid'],
        'startDate': min(dates), 'endDate': max(dates),
    })
    d = zql_get(ZQL_MATCHES.format(qs=qs))
    if str(d.get('errorCode')) != '0':
        return {}
    out: dict[str, list[dict]] = {}
    for g in (d.get('value') or {}).get('matchList') or []:
        date = str(g.get('matchDate') or '')
        if date not in dates:
            continue
        rows = []
        for m in g.get('subMatchList') or []:
            home = canonical_team_name(str(m.get('homeAbbCnName') or '').strip())
            away = canonical_team_name(str(m.get('awayAbbCnName') or '').strip())
            if not home or not away:
                continue
            rows.append({
                'code': '',
                'time': (str(m.get('matchTime') or ''))[:5] or '—',
                'league': league['name'],
                'home': home,
                'away': away,
                'jc': 0,
                'fid': None,
                'zid': m.get('uniformMatchId'),
                'st': zql_status(m.get('wbsjMatchScDesc')),
            })
        if rows:
            out[date] = rows
    return out


def fetch_zql(dates: set[str]) -> dict[str, list[dict]]:
    leagues = zql_leagues()
    out: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(zql_rows, lg, dates): lg for lg in leagues}
        for fu, lg in futures.items():
            try:
                part = fu.result()
            except Exception as e:
                print(f"[fixtures] 竞彩资料 {lg['name']} 异常 "
                      f"{type(e).__name__}: {e}，跳过")
                continue
            for d, rows in part.items():
                out.setdefault(d, []).extend(rows)
    return out


# ---------------- 合并 ----------------

def norm(s: str) -> str:
    return re.sub(r"[\s\u3000·\-()（）队]", "", s or "")


def same(a: str, b: str) -> bool:
    """队名双向包含兜底：简称 / 全称 / 译名差异都能对上。"""
    a, b = norm(a), norm(b)
    return bool(a and b and (a == b or (len(a) >= 2 and len(b) >= 2
                                        and (a in b or b in a))))


def alike(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def likely_same(r: dict, z: dict) -> bool:
    """竞彩官方简称与全量库全称对同一场的兜底：同开赛时间 + 双方队名相似。"""
    if same(r.get("home") or "", z.get("home") or "") \
            and same(r.get("away") or "", z.get("away") or ""):
        return True
    if (r.get("time") or "") != (z.get("time") or ""):
        return False
    hr = alike(r.get("home") or "", z.get("home") or "")
    ar = alike(r.get("away") or "", z.get("away") or "")
    lr = alike(r.get("league") or "", z.get("league") or "")
    return min(hr, ar) >= 0.33 and hr + ar >= 1.0 and lr >= 0.33


def merge(jc: dict[str, list[dict]], full: dict[str, list[dict]],
          zql: dict[str, list[dict]] | None = None) -> dict[str, list[dict]]:
    days: dict[str, list[dict]] = {}
    zql = zql or {}
    for d in sorted({*jc, *full, *zql}):
        jc_rows = jc.get(d) or []
        rows = [dict(r) for r in (full.get(d) or [])]
        for z in zql.get(d) or []:
            hit = next((r for r in rows if likely_same(r, z)), None)
            if hit:
                hit["zid"] = z.get("zid")
                if not hit.get("st") or hit["st"] == "未开赛":
                    hit["st"] = z.get("st") or hit.get("st")
                if not hit.get("time") or hit["time"] == "—":
                    hit["time"] = z.get("time") or hit.get("time")
            else:
                rows.append(dict(z))
        for r in rows:
            for j in jc_rows:
                if same(r.get("home") or "", j["home"]) and same(r.get("away") or "", j["away"]):
                    r.update(code=j["code"], mid=j.get("mid"),
                             status=j.get("status"), jc=1)
                    break
        matched = {r["code"] for r in rows if r.get("code")}
        for j in jc_rows:
            if j["code"] not in matched:
                rows.append({**j, "jc": 1, "fid": None, "st": "未开赛"})
        rows.sort(key=lambda r: (r.get("time") or "", r.get("code") or ""))
        if rows:
            days[d] = rows
    return days


def backfill_crest_ids(days: dict[str, list[dict]]) -> int:
    """竞彩独有场次没有上游队徽编号，按队名从同一批赛程里借一个。"""
    pool: dict[str, str] = {}
    for rows in days.values():
        for r in rows:
            for name, tid in ((r.get("home"), r.get("hid")),
                              (r.get("away"), r.get("aid"))):
                if name and tid and name not in pool:
                    pool[name] = tid
    n = 0
    for rows in days.values():
        for r in rows:
            for name_key, id_key in (("home", "hid"), ("away", "aid")):
                if not r.get(id_key):
                    tid = pool.get(r.get(name_key) or "")
                    if tid:
                        r[id_key] = tid
                        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不写盘")
    ap.add_argument("--jc-only", action="store_true", help="跳过全量赛程，应急降级")
    ap.add_argument("--no-zq", action="store_true", help="跳过竞彩官方联赛资料")
    args = ap.parse_args(argv)

    text = fetch_odds_from_lottery()
    if not text:
        print("[fixtures] 竞彩抓取失败，保留上一份文件不动")
        return 1
    jc = parse_jc(text)
    if not jc:
        print("[fixtures] 竞彩解析结果为空，保留上一份文件不动")
        return 1
    today = dt.date.today()
    keep = {(today + dt.timedelta(days=i)).isoformat() for i in range(JC_KEEP_DAYS)}
    jc = {d: rows for d, rows in jc.items() if d in keep}
    future = {(today + dt.timedelta(days=i)).isoformat()
              for i in range(FUTURE_DAYS)}

    full: dict[str, list[dict]] = {}
    zql: dict[str, list[dict]] = {}
    source = "jc+full+zq"
    if not args.jc_only:
        try:
            full = fetch_full()
        except Exception as e:
            print(f"[fixtures] 全量赛程不可用（{type(e).__name__}: {e}），降级为竞彩源")
        if not full:
            print("[fixtures] 全量赛程为空，降级为竞彩源")
    else:
        source = "jc"
    if not args.no_zq and not args.jc_only:
        try:
            zql = fetch_zql(future)
        except Exception as e:
            print(f"[fixtures] 竞彩联赛资料不可用（{type(e).__name__}: {e}），跳过")
    if not full and not zql:
        source = "jc"

    days = merge(jc, full, zql)
    if not days:
        print("[fixtures] 合并结果为空，保留上一份文件不动")
        return 1
    filled = backfill_crest_ids(days)
    total = sum(len(v) for v in days.values())
    jc_n = sum(1 for v in days.values() for r in v if r.get("jc"))
    crested = sum(1 for v in days.values() for r in v
                  if r.get("hid") and r.get("aid"))

    if args.dry_run:
        for d, rows in sorted(days.items()):
            print(f"--- {d} {len(rows)} 场（竞彩 {sum(1 for r in rows if r.get('jc'))}）")
            for r in rows[:4]:
                print(f"  {r['time']} {r['league']:<8} {r['home']} vs {r['away']}"
                      f"  {'竞彩 ' + r['code'] if r['code'] else '仅赛程'}")
        print(f"[fixtures] dry-run：{len(days)} 天 / {total} 场 / 竞彩 {jc_n}")
        return 0

    payload = {
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": source,
        "days": days,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    summary = "、".join(f"{d[5:]} {len(rows)} 场" for d, rows in sorted(days.items()))
    print(f"[fixtures] {len(days)} 天 / {total} 场（竞彩 {jc_n}）→ {OUT.name}")
    print(f"[fixtures] 队徽编号覆盖 {crested}/{total} 场（借名回填 {filled} 处）")
    print(f"[fixtures] {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
