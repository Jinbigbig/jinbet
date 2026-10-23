#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘口时序采集：把当天场次的竞彩赔率/让球按时间点留档，供「初盘→临场」变化曲线使用。

官方只给当前值，没有历史，所以曲线靠多次抓取累积。每日三个时点采集：
11:10（盘口刚开＝初盘）、14:00（预测流水线内）、19:00（临场）。
跨时点即使赔率没变也记点，曲线上才看得到「到点无变化」。

产出 odds_ticks.json：
    {"updated": "2026-10-23 18:00",
     "ticks": {"2026-10-23_波鸿_沃夫斯堡": [{"t": "2026-10-23 18:00", "胜": 2.3, "平": 3.6,
                                    "负": 2.4, "让球": [{"handicap": "-1", "胜": 4.5, ...}]}]}}

用法：
    python _fetch_odds_ticks.py            # 抓一次
    python _fetch_odds_ticks.py --dry-run  # 只打印不写盘
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

BASE = Path(__file__).resolve().parent
OUT = BASE / "odds_ticks.json"
KEEP_DAYS = 7          # 只留最近 7 天的点，文件不至于无限长

sys.path.insert(0, str(BASE))
from update_odds_net import fetch_odds_from_lottery, parse_lottery_json  # noqa: E402


def _num(v):
    try:
        return round(float(v), 3)
    except (TypeError, ValueError):
        return None


def _point(stamp: str, rec: dict) -> dict:
    rq = []
    for r in (rec.get("让球") or []):
        if not isinstance(r, dict):
            continue
        rq.append({
            "handicap": str(r.get("handicap", "") or ""),
            "胜": _num(r.get("胜")),
            "平": _num(r.get("平")),
            "负": _num(r.get("负")),
        })
    return {
        "t": stamp,
        "胜": _num(rec.get("胜")),
        "平": _num(rec.get("平")),
        "负": _num(rec.get("负")),
        "让球": rq,
    }


def _same(a: dict, b: dict) -> bool:
    """赔率与让球都没变。"""
    keys = ("胜", "平", "负")
    if any(a.get(k) != b.get(k) for k in keys):
        return False
    return (a.get("让球") or []) == (b.get("让球") or [])


def _same_hour(t1: str, t2: str) -> bool:
    """同一小时内（精确到小时）。"""
    return str(t1)[:13] == str(t2)[:13]


def main() -> int:
    dry = "--dry-run" in sys.argv
    raw = fetch_odds_from_lottery()
    if not raw:
        print("[盘口时序] 源不可用，跳过本次")
        return 0
    odds, _schedule = parse_lottery_json(raw)
    if not odds:
        print("[盘口时序] 解析后无赔率，跳过本次")
        return 0

    now = dt.datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M")
    data = {"updated": stamp, "ticks": {}}
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
            data.setdefault("ticks", {})
        except (json.JSONDecodeError, OSError):
            pass
    data["updated"] = stamp
    ticks: dict[str, list] = data["ticks"]

    cutoff = (now - dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    added = same = moved = 0
    for key, rec in odds.items():
        point = _point(stamp, rec)
        if not any(point[k] is not None for k in ("胜", "平", "负")):
            continue
        seq = [p for p in ticks.get(key, []) if str(p.get("t", ""))[:10] >= cutoff]
        # 同一小时里重复跑且数值没变才跳过；跨小时一律记点——三个采集时点都要在曲线上
        if seq and _same_hour(seq[-1].get("t", ""), stamp) and _same(seq[-1], point):
            same += 1
        else:
            if seq and not _same(seq[-1], point):
                moved += 1
            seq.append(point)
            added += 1
        ticks[key] = seq

    data["ticks"] = {k: v for k, v in ticks.items()
                     if v and any(str(p.get("t", ""))[:10] >= cutoff for p in v)}

    if dry:
        print(f"[盘口时序] dry-run：{len(odds)} 场，新增 {added} 点，未变 {same} 点")
        return 0

    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    multi = sum(1 for v in data["ticks"].values() if len(v) >= 2)
    print(f"[盘口时序] {stamp} 场次 {len(data['ticks'])} · 新增 {added} 点 · "
          f"赔率变动 {moved} 场 · 同小时未变 {same} 点 · 已有 ≥2 点 {multi} 场 → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
