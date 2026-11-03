#!/usr/bin/env python3
"""已发布预测 vs 实际赛果：线上准确率评估（方向 / 比分 / 校准）。

为什么单独一个脚本：模型参数（MARKET_W、Platt、λ 窗口）过去都是靠一次性探针脚本
调出来的，那些脚本早已和当前快照格式脱节。这里只读 `predictions/*/pred_snapshot.json`
与 `results_data.json`，跑的是**线上真值**，不重放引擎，所以任何参数改动的效果都能
用同一把尺子量。

用法：
    python _eval_live.py              # 全样本 + 按月 + 近 10 天
    python _eval_live.py --recent 20  # 只看最近 20 个比赛日
    python _eval_live.py --by star    # 按星级/领先幅度拆开看

输出口径：
    方向     = argmax(主/平/客) 是否等于实际赛果
    首选     = top_score 是否等于实际比分
    头条     = headline 是否等于实际比分（发布用，含同日去重）
    双档     = top_scores 前两个含实际比分
    市场基准 = 按收盘赔率（快照 odds 字段）选热门
    logL     = 多分类对数损失（越接近市场基准越好；高于基准说明概率被推离真值）
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def _load(name, default=None):
    p = os.path.join(BASE, name)
    if not os.path.exists(p):
        return default if default is not None else {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def build_rows():
    res = _load("results_data.json")
    idx = {}
    for k, v in res.items():
        idx[(k.split("_")[0], v.get("home"), v.get("away"))] = v
    rows = []
    for path in sorted(glob.glob(os.path.join(BASE, "predictions", "*", "pred_snapshot.json"))):
        day = os.path.basename(os.path.dirname(path))
        with open(path, encoding="utf-8") as fh:
            snap = json.load(fh)
        for m in snap.get("matches") or []:
            r = idx.get((day, m.get("home"), m.get("away")))
            if not r:
                continue
            try:
                hg, ag = [int(x) for x in (r.get("fullScore") or "").replace("-", ":").split(":")]
            except ValueError:
                continue
            act = "H" if hg > ag else ("D" if hg == ag else "A")
            score = f"{hg}:{ag}"
            ph, pd, pa = ((m.get("prob_" + k) or 0) / 100 for k in ("home", "draw", "away"))
            pred = max((("H", ph), ("D", pd), ("A", pa)), key=lambda x: x[1])[0]
            mkt = None
            o = m.get("odds") or {}
            try:
                oh, od, oa = (float(o.get(k) or 0) for k in ("胜", "平", "负"))
                if min(oh, od, oa) > 1:
                    s = 1 / oh + 1 / od + 1 / oa
                    mkt = (1 / oh / s, 1 / od / s, 1 / oa / s)
            except (TypeError, ValueError):
                mkt = None
            top2 = [t.get("score") for t in (m.get("top_scores") or [])[:2]]
            rows.append(dict(
                day=day, league=m.get("league") or "?", act=act, score=score,
                pred=pred, p={"H": ph, "D": pd, "A": pa}, mkt=mkt,
                stars=m.get("stars"),
                top_ok=m.get("top_score") == score,
                head_ok=(m.get("headline") or {}).get("score") == score,
                q2=score in top2,
            ))
    return rows


def summarize(name, rows):
    n = len(rows)
    if not n:
        return
    dir_ok = sum(r["pred"] == r["act"] for r in rows) / n * 100
    top = sum(r["top_ok"] for r in rows) / n * 100
    head_rows = [r for r in rows if r.get("head_ok") is not None]
    head = sum(r["head_ok"] for r in head_rows) / max(1, len(head_rows)) * 100
    q2 = sum(r["q2"] for r in rows) / n * 100
    logl = -sum(math.log(max(r["p"][r["act"]], 1e-9)) for r in rows) / n
    mk = [r for r in rows if r.get("mkt")]
    macc = sum(max(zip("HDA", r["mkt"]), key=lambda x: x[1])[0] == r["act"]
               for r in mk) / max(1, len(mk)) * 100
    print(f"{name:<12} n={n:4d}  方向 {dir_ok:5.1f}%  首选 {top:5.1f}%  头条 {head:5.1f}%  "
          f"双档 {q2:5.1f}%  logL {logl:.4f}  市场 {macc:5.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int, default=0, help="只看最近 N 个比赛日")
    ap.add_argument("--by", dest="by", choices=("star", "league", "month"), default=None)
    args = ap.parse_args()

    rows = build_rows()
    if not rows:
        print("没有可用样本：先确认 predictions/*/pred_snapshot.json 与 results_data.json 能对上")
        return
    days = sorted({r["day"] for r in rows})
    if args.recent:
        rows = [r for r in rows if r["day"] >= days[-args.recent]]

    print(f"样本 {len(rows)} 场 / {len({r['day'] for r in rows})} 个比赛日\n")
    summarize("全部", rows)
    if not args.recent:
        groups = collections.defaultdict(list)
        for r in rows:
            groups[r["day"][:7]].append(r)
        for k in sorted(groups):
            summarize("月 " + k, groups[k])
    for k in (10, 20, 30):
        if len(days) >= k:
            summarize(f"近{k}天", [r for r in rows if r["day"] >= days[-k]])

    if args.by == "star":
        print()
        for s in (1, 2, 3, 4, 5):
            summarize(f"{s}★", [r for r in rows if r.get("stars") == s])
    elif args.by == "league":
        print()
        groups = collections.defaultdict(list)
        for r in rows:
            groups[r["league"]].append(r)
        for lg, rs in sorted(groups.items(), key=lambda x: -len(x[1]))[:12]:
            summarize(lg, rs)


if __name__ == "__main__":
    main()
