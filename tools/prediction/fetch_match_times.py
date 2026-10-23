#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取竞彩场次开赛时间 → match_times.json

数据源：网易彩票竞彩赛程接口（sports.163.com/caipiao/api/web/match/list/jingcai/matchList/1）
        该接口自带 matchTime（开赛时间，Unix 毫秒，北京时间），赛果链路 fetch_163_results 已在用同一接口。

输出结构：
{
  "date": "2026-10-23",          # 本文件对应的投注周期日（报告侧必须校验，防跨日脏数据）
  "updated": "2026-10-23 10:12",
  "source": "网易彩票竞彩赛程",
  "times": {
     "周四001": {"ko": "2026-10-22 00:45", "label": "00:45", "day": 0},
     ...
  },
  "miss": []                      # 接口未覆盖、缺时间的编号
}

label 相对 date 生成：同日 → "HH:MM"；次日 → "次日 HH:MM"；其余 → "MM-DD HH:MM"。
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "match_times.json")
API = ("https://sports.163.com/caipiao/api/web/match/list/jingcai/matchList/1?days=")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://sports.163.com/caipiao/match/football/jczq",
}

BEIJING = dt.timezone(dt.timedelta(hours=8))


def _name(x):
    """网易接口 homeTeam/guestTeam 可能是 dict 或 str，统一取队名。"""
    if isinstance(x, dict):
        for k in ("name", "teamName", "shortName", "cnName", "teamShortName"):
            if x.get(k):
                return str(x[k])
        return ""
    return str(x or "")


def _fetch(day: str) -> list:
    """拉某一天中午起的赛程（接口返回当日 + 次日的全部可售/已售场次）。"""
    url = API + urllib.parse.quote(f"{day} 12:00:00")
    req = urllib.request.Request(url, data=b"", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return (json.loads(raw).get("data") or [])


def _label(kick: dt.datetime, base_day: dt.date) -> tuple:
    """返回 (label, day_offset)。"""
    off = (kick.date() - base_day).days
    hm = kick.strftime("%H:%M")
    if off == 0:
        return hm, 0
    if off == 1:
        return f"次日 {hm}", 1
    if off == -1:
        return f"前日 {hm}", -1
    return f"{kick.strftime('%m-%d')} {hm}", off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat(),
                    help="投注周期日 YYYY-MM-DD，默认今天")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    base_day = dt.date.fromisoformat(args.date)

    rows = {}
    # 抓当天 + 前后各一天：竞彩场次常跨零点（周五002 实际周六 00:30 开赛），
    # 且历史复盘时报告的「次日凌晨场」落在后一天。
    for delta in (-1, 0, 1):
        day = (base_day + dt.timedelta(days=delta)).isoformat()
        try:
            data = _fetch(day)
        except Exception as e:
            if not args.quiet:
                print(f"  [警告] {day} 赛程拉取失败：{type(e).__name__}")
            continue
        for m in data:
            num = (m.get("jcNum") or "").strip()
            ms = m.get("matchTime")
            if not num or not ms:
                continue
            try:
                kick = dt.datetime.fromtimestamp(int(ms) / 1000.0, BEIJING)
            except Exception:
                continue
            prev = rows.get(num)
            if prev is None or kick < prev:
                rows[num] = kick

    times = {}
    misses = []
    for num, kick in rows.items():
        label, off = _label(kick, base_day)
        times[num] = {
            "ko": kick.strftime("%Y-%m-%d %H:%M"),
            "label": label,
            "day": off,
        }

    payload = {
        "date": base_day.isoformat(),
        "updated": dt.datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
        "source": "网易彩票竞彩赛程",
        "times": times,
        "miss": misses,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    if not args.quiet:
        same = sum(1 for v in times.values() if v["day"] == 0)
        nxt = sum(1 for v in times.values() if v["day"] == 1)
        print(f"[开赛时间] {payload['date']} 收到 {len(times)} 场"
              f"（当日 {same} / 次日 {nxt}）→ match_times.json")
        sample = sorted(times.items())[:3]
        if sample:
            print("  样例：" + " ｜ ".join(f"{k}={v['label']}" for k, v in sample))


if __name__ == "__main__":
    main()
