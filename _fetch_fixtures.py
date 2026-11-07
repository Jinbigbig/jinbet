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
import json
import re
import sys
import urllib.parse
import urllib.request
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
        out.append({
            "code": "",
            "time": (t.group(1).strip() if t else "")[:5] or "—",
            "league": lg.group(1).strip() if lg else "",
            "home": home,
            "away": away,
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


# ---------------- 合并 ----------------

def norm(s: str) -> str:
    return re.sub(r"[\s\u3000·\-()（）队]", "", s or "")


def same(a: str, b: str) -> bool:
    """队名双向包含兜底：简称 / 全称 / 译名差异都能对上。"""
    a, b = norm(a), norm(b)
    return bool(a and b and (a == b or (len(a) >= 2 and len(b) >= 2
                                        and (a in b or b in a))))


def merge(jc: dict[str, list[dict]], full: dict[str, list[dict]]) -> dict[str, list[dict]]:
    days: dict[str, list[dict]] = {}
    for d in sorted({*jc, *full}):
        jc_rows = jc.get(d) or []
        rows = [dict(r) for r in (full.get(d) or [])]
        for r in rows:
            for j in jc_rows:
                if same(r["home"], j["home"]) and same(r["away"], j["away"]):
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不写盘")
    ap.add_argument("--jc-only", action="store_true", help="跳过全量赛程，应急降级")
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

    full: dict[str, list[dict]] = {}
    source = "jc+full"
    if not args.jc_only:
        try:
            full = fetch_full()
        except Exception as e:
            print(f"[fixtures] 全量赛程不可用（{type(e).__name__}: {e}），降级为纯竞彩")
        if not full:
            source = "jc"
            print("[fixtures] 全量赛程为空，降级为纯竞彩")
    else:
        source = "jc"

    days = merge(jc, full)
    if not days:
        print("[fixtures] 合并结果为空，保留上一份文件不动")
        return 1
    total = sum(len(v) for v in days.values())
    jc_n = sum(1 for v in days.values() for r in v if r.get("jc"))

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
    print(f"[fixtures] {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
